"""Exercise the production loop and handlers against a strict memory SQL boundary.

Only the clock, settings budget and daily-spend aggregate are substituted.
Observation queries, source policy, ownership filters, typed argument validation,
coverage, context retrieval, constraints, audit, caching and answer validation run
production code. This is not a substitute for PostgreSQL integration tests.
"""

import copy
import json
import re
import time
from contextlib import ExitStack
from dataclasses import dataclass
from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList

from app.agent import loop, tools
from app.agent.entrypoint import _system_block
from app.core.llm import LLMResponse, ToolCallRequest
from app.models.ai import AgentToolCall, TokenUsage
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.coach import UserContextDoc, UserEvent
from app.models.lab import AthleteEntry, ChangeDraft, Observation
from app.models.user import User
from app.services import analytics, changes, evidence
from evals.scenarios import NOW, Scenario


class FixedDateTime(type(NOW)):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def _value(expression, row, store):
    if isinstance(expression, BindParameter):
        return expression.value
    if getattr(expression, "__visit_name__", "") == "true":
        return True
    if getattr(expression, "__visit_name__", "") == "false":
        return False
    if getattr(expression, "__visit_name__", "") == "null":
        return None
    if getattr(expression, "__visit_name__", "") == "select":
        return [r[0] for r in MemorySession(store)._select(expression)]
    if getattr(expression, "__visit_name__", "") == "grouping" and getattr(expression.element, "is_select", False):
        return [r[0] for r in MemorySession(store)._select(expression.element)]
    if hasattr(expression, "table") and expression.table.name != row.__table__.name:
        for model, candidates in store.rows.items():
            if model.__table__.name == expression.table.name:
                fk = getattr(row, "discipline_id", None) if model is Discipline else getattr(row, "training_plan_id", None)
                joined = next((r for r in candidates if r.id == fk), None)
                if joined is not None:
                    return getattr(joined, expression.name)
        return None
    if hasattr(expression, "name") and hasattr(row, expression.name):
        return getattr(row, expression.name)
    raise AssertionError(f"Unsupported fixture SQL value: {type(expression).__name__}")


def _matches(expression, row, store):
    if isinstance(expression, BooleanClauseList):
        values = [_matches(c, row, store) for c in expression.clauses]
        if expression.operator is operators.and_:
            return all(values)
        if expression.operator is operators.or_:
            return any(values)
    if isinstance(expression, BinaryExpression):
        left, op = _value(expression.left, row, store), expression.operator
        if op is operators.between_op:
            low, high = [_value(c, row, store) for c in expression.right.clauses]
            return low <= left <= high
        right = _value(expression.right, row, store)
        if op in (operators.eq, operators.is_):
            return left == right
        if op is operators.in_op:
            return left in right
        if op is operators.not_in_op:
            return left not in right
        if op in (operators.ge, operators.le, operators.gt, operators.lt):
            return op(left, right)
        if op is operators.ilike_op:
            # Search fixtures use plain query strings; escaping is still done by
            # the actual handler. Unknown LIKE syntax is deliberately unsupported.
            needle = right.strip("%").replace("\\%", "%").replace("\\_", "_")
            return needle.casefold() in (left or "").casefold()
    raise AssertionError(f"Unsupported fixture SQL predicate: {type(expression).__name__}")


class MemoryStore:
    def __init__(self, scenario):
        self.rows = {User: [User(id=1, timezone="UTC", locale="en")]}
        self.writes = []
        self.queries = []
        self.rows[Observation] = [Observation(
            id=r["id"], user_id=r["user_id"], metric=r["metric"],
            value={"value": r["value"]}, unit=r["unit"], origin=r["origin"],
            acquisition="synthetic_fixture", source_record_id=f"fixture:{r['id']}",
            measured_at=r["measured_at"], fetched_at=NOW,
            local_date=r["measured_at"].date(), timezone="UTC", revision=1,
            current=True, availability="available", quality_flags=[],
            metadata_json=r["metadata"], content_hash=f"synthetic:{r['id']}",
        ) for r in scenario.observations]
        self.rows[UserContextDoc] = [UserContextDoc(
            id=i + 1, user_id=1, doc_kind="profile", content=text,
            updated_by="user", updated_at=NOW,
        ) for i, text in enumerate(scenario.docs)]
        self.rows[AthleteEntry] = []
        self.rows[UserEvent] = []
        self.rows[Discipline] = [Discipline(id=1, name="road_cycling")]
        self.rows[Activity] = [Activity(id=a["id"], user_id=1, discipline_id=1,
            local_date=NOW.date(), start_time=NOW, duration_s=a["duration_s"],
            training_load=None, source_metrics={}) for a in scenario.activities]
        self.rows[ActivitySourceLink] = [ActivitySourceLink(id=i + 1,
            user_id=1, activity_id=a["id"], source=origin, external_id=f"fixture:{a['id']}")
            for a in scenario.activities for i, origin in enumerate(a["origins"])]
        if checkin := scenario.constraints.get("daily_checkin"):
            self.rows[AthleteEntry].append(AthleteEntry(
                id=1, user_id=1, kind="daily_checkin", date=NOW.date(), payload=checkin,
            ))
        if event := scenario.constraints.get("event"):
            self.rows[UserEvent].append(UserEvent(
                id=1, user_id=1, title="Synthetic priority race", kind=event["kind"],
                starts_at=NOW + timedelta(days=event.get("days_away", 0)),
                priority=event["priority"], taper_days=event["taper_days"],
            ))

    def sessionmaker(self):
        return MemorySession(self)


class MemorySession:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, ident):
        return next((r for r in self.store.rows.get(model, []) if r.id == ident), None)

    def _select(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is None:
            raise AssertionError("Aggregate queries must use the explicit fixture boundary")
        self.store.queries.append(str(statement))
        rows = list(self.store.rows.get(entity, []))
        rows = [r for r in rows if all(_matches(c, r, self.store) for c in statement._where_criteria)]
        for ordering in reversed(statement._order_by_clauses):
            column = getattr(ordering, "element", ordering)
            reverse = getattr(ordering, "modifier", None) is operators.desc_op
            rows.sort(key=lambda r: getattr(r, column.name), reverse=reverse)
        if statement._limit_clause is not None:
            rows = rows[:statement._limit_clause.value]
        return [tuple(row if desc["expr"] is desc["entity"] else _value(desc["expr"], row, self.store)
                      for desc in statement.column_descriptions) for row in rows]

    async def scalars(self, statement):
        rows = [r[0] for r in self._select(statement)]
        return SimpleNamespace(all=lambda: rows)

    async def execute(self, statement, params=None):
        if str(statement) == "SELECT pg_advisory_xact_lock(:key)":
            return SimpleNamespace(all=lambda: [])
        rows = self._select(statement)
        return SimpleNamespace(all=lambda: rows)

    async def scalar(self, statement, params=None):
        if params and "SELECT md5(" in str(statement):
            table = re.search(r" FROM (\w+)", str(statement)).group(1)
            rows = [r for model, items in self.store.rows.items() if model.__table__.name == table
                    for r in items if r.user_id == params["owner"]]
            return evidence.digest([[r.id, getattr(r, "content_hash", None)] for r in rows])
        rows = (await self.scalars(statement)).all()
        return rows[0] if rows else None

    def add(self, row):
        self.store.writes.append(row)

    async def flush(self):
        for row in self.store.writes:
            if getattr(row, "id", None) is None:
                row.id = 1000 + self.store.writes.index(row)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class ReplayClient:
    """Recorded responses drive real runtime defenses, never a provider endpoint."""
    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = []
        self.index = 0
        self.responses = []

    async def complete(self, *, messages, system, tier, tools):
        self.calls.append(copy.deepcopy({"messages": messages, "system": system,
                                         "tier": tier, "tools": tools}))
        if tools is not None and self.index < len(self.scenario.batches):
            batch = self.scenario.batches[self.index]
            response = LLMResponse(content=None, model="deterministic-replay",
                tokens_in=100, tokens_out=30,
                tool_calls=[ToolCallRequest(f"{self.index}:{i}", name, args)
                            for i, (name, args) in enumerate(batch)])
            self.index += 1
        else:
            response = LLMResponse(content=json.dumps(self.scenario.answer),
                                   model="deterministic-replay", tokens_in=120, tokens_out=60)
        self.responses.append(response)
        return response


class RecordingClient:
    def __init__(self, client):
        self.client, self.calls, self.responses = client, [], []

    async def complete(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        response = await self.client.complete(**kwargs)
        self.responses.append(response)
        return response


@dataclass
class Trace:
    result: object
    responses: list
    model_calls: list
    persisted_tools: list
    usage: list
    queries: list[str]
    latency_ms: int
    persisted_drafts: list
    live: bool = False


async def run_scenario(scenario: Scenario, *, client=None) -> Trace:
    store = MemoryStore(scenario)
    model = RecordingClient(client) if client is not None else ReplayClient(scenario)

    async def daily_spend(*args):
        return Decimal(0)

    async def deny_external_job(*args, **kwargs):
        raise evidence.EvidenceError("POLICY_DENIED", "External jobs are disabled in evaluation")

    started = time.monotonic()
    with ExitStack() as stack:
        for module in (loop, tools, evidence, analytics, changes):
            stack.enter_context(patch.object(module, "datetime", FixedDateTime))
        stack.enter_context(patch.object(loop, "get_settings", return_value=SimpleNamespace(daily_token_budget_usd=1)))
        stack.enter_context(patch.object(loop, "user_day_spend", daily_spend))
        # Even optional live model trials operate only on synthetic memory data.
        # Maintenance queueing is the one tool boundary that can contact a broker.
        if client is not None:
            from app.services import jobs
            stack.enter_context(patch.object(jobs, "request_job", deny_external_job))
            stack.enter_context(patch.object(jobs, "request_analysis", deny_external_job))
        snapshot = {
            "profile": {"timezone": "UTC", "local_today": str(NOW.date()), "locale": "en"},
            "source_policy": "ai_eligible_v1", "snapshot_revision": "synthetic-fixture",
            "daily_decision": {"state": "hold" if scenario.id == "illness_pain" else "review",
                               "constraints": scenario.constraints},
            "context_docs": [{"kind": "profile", "content": text} for text in scenario.docs],
        }
        result = await loop.run_agent_loop(store.sessionmaker, model,
            user_id=1, session_id=1, text=scenario.question, system=_system_block(snapshot),
            tier="cheap", today=NOW.date(), max_iterations=loop.MAX_ITERATIONS)
    return Trace(result, model.responses, model.calls,
                 [r for r in store.writes if isinstance(r, AgentToolCall)],
                 [r for r in store.writes if isinstance(r, TokenUsage)], store.queries,
                 int((time.monotonic() - started) * 1000),
                 [r for r in store.writes if isinstance(r, ChangeDraft)], client is not None)
