# Coach runtime evaluations

From `backend`, run:

```bash
uv run python -m evals.run
uv run python -m evals.run --output-dir /tmp/apex-evals
uv run python -m evals.run --scenario missing_hrv --scenario attempted_self_approval
```

The default is deterministic replay through the production agent loop and typed
tool handlers. It uses synthetic ORM fixtures and a strict memory SQL boundary,
never PostgreSQL, Redis, a provider, or a maintenance queue. It exercises argument
validation, ownership and restricted-source filters, observations and coverage,
context search, constraints, canonical activity deduplication, draft creation,
audit receipts, read caching, bounded closure and final answer validation.
The memory boundary also substitutes SQL fingerprint aggregates and advisory
locks for draft creation; it does not test transaction isolation or persistence.

`report.json` contains replies, grounding receipts, tool audits, per-scorer
metrics, model identities and failures. `report.md` provides the comparison
table and failed checks. Both are written to `evals/artifacts` by default;
artifacts are ignored by Git. Exit status is zero only when all selected
scenarios pass. Model errors fail the scenario; results are never filled in.
Observed wall-clock and tool timings can vary between otherwise identical runs.

The 26 references explicitly cover normal recovery, missing HRV, stale data,
conflicting providers, poor sleep, high load, taper, strength/endurance
interference, illness and pain, missing power, restricted Strava and derivatives,
malicious documents, foreign IDs, attempted self-approval, unsupported numeric
and causal claims, excessive calls, subjective soreness, insufficient baseline,
device change, manual observations, journal/wearable contradictions, duplicated
activities, future events, recommendation modification and unsafe medical advice.

Reusable scorers check exact evidence values and units, common metric/value
bindings in prose, handles returned in this turn, lexical safety and causal
calibration, source eligibility, denied authority tools, repeated read execution,
reported tokens and usage receipts, estimated cost, observed latency, selected
canonical output fields and persisted draft status. Negative mutation tests show
that these scorers reject corrupted traces. Scenario limits are explicit fixture
budgets, not validated product quality thresholds.

Replay is a runtime regression suite, **not observed model quality**. The safety
rubric is lexical, not a clinical or semantic judge. Fixture usage numbers are
synthetic: estimated production cost is calculated from application rates, while
actual provider spend is zero. Offline latency measures local overhead and
cannot predict a live provider's latency.

The hermetic test module overrides the repository's destructive database and
Redis autouse fixtures locally. It can be run without services or schema reset:

```bash
uv run python -m pytest tests/test_agent_evals.py -q
```

Optional live trials require all three explicit gates:

```bash
APEX_EVALS_ALLOW_LIVE=1 LLM_PROVIDER_CHEAP=your-explicit-model \
  uv run python -m evals.run --live --allow-paid-live --scenario normal_recovery
```

Configure the normal application's endpoint and key for that model separately.
The live option can incur provider charges. It uses the same synthetic memory
fixtures, denies external maintenance/analysis queueing, records actual returned
model identities and reported token usage, and does not claim actual billing
amounts. Reference scripts are not used as live answers. Live scoring accepts a
safe grounded or fail-closed answer instead of requiring the scripted attack's
exact invalid status, tool selection, or draft count. No live trial is part of
the default command or tests.
