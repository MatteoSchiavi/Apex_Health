"""Real client requests and bounded coach retrieval, without live provider calls."""
import json
from datetime import UTC, datetime, timedelta, date
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.llm import LiveGLMClient, LLMResponse, LLMUnavailableError, ToolCallRequest, resolve_llm_endpoint, parse_completion
from app.core.db import sessionmaker
from app.agent.loop import run_agent_loop, _assistant_tool_call_message
from app.agent.tools import TOOL_REGISTRY, ToolContext
from app.models.chat import AiChatSession
from app.queries.usage import estimate_llm_cost_usd
from tests.helpers.ai import FixtureAgentLLMClient


def settings(**overrides):
    return Settings(_env_file=None, database_url='postgresql+asyncpg://unused', redis_url='redis://unused',
                    session_secret='test', encryption_key='test', owner_email='test@example.com', owner_password='test', **overrides)


async def test_deepseek_key_only_calls_correct_endpoint_and_models_for_all_tiers():
    s = settings(deepseek_api_key='test-deepseek-key')
    base, key, model = resolve_llm_endpoint(s, 'cheap')
    assert (base, key, model) == ('https://api.deepseek.com', 'test-deepseek-key', 'deepseek-flash')
    assert resolve_llm_endpoint(s, 'free') == (base, key, model)
    assert resolve_llm_endpoint(s, 'powerful') == (base, key, model)
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={'model':model,'choices':[{'message':{'content':'Grounded reply'}}],
                                       'usage':{'prompt_tokens':10,'completion_tokens':2,'prompt_cache_hit_tokens':6}})
    client = LiveGLMClient('', '', model, model, api_key_cheap=key, api_base_cheap=base, api_key_powerful=key, api_base_powerful=base)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        for tier in ('free','cheap','powerful'):
            result = await client.complete([{'role':'user','content':'Recovery summary'}], tier=tier)
            assert result.model == model and result.cached_tokens == 6
        assert len(seen) == 3
        for request in seen:
            assert str(request.url) == 'https://api.deepseek.com/chat/completions'
            assert request.headers['authorization'] == 'Bearer test-deepseek-key'
            assert json.loads(request.content)['thinking'] == {'type':'disabled'}
    finally:
        await client.aclose()


def test_explicit_tier_vendor_and_custom_endpoint_never_receive_another_vendors_key():
    s = settings(deepseek_api_key='deepseek', glm_api_key='glm', llm_provider_powerful='glm-5.2')
    assert resolve_llm_endpoint(s,'powerful')[1:] == ('glm','glm-5.2')
    s.llm_api_base_cheap = 'https://other.example.com/v1'
    with pytest.raises(LLMUnavailableError): resolve_llm_endpoint(s,'cheap')
    s.llm_api_key_cheap = 'other'; s.llm_provider_cheap = 'explicit-model'
    assert resolve_llm_endpoint(s,'cheap') == ('https://other.example.com/v1','other','explicit-model')


def test_deepseek_routing_calls_have_real_cost_and_reasoning_is_preserved_for_tools():
    assert estimate_llm_cost_usd('free',1_000_000,1_000_000,model='deepseek-flash') == Decimal('1.5')
    response = parse_completion({'choices':[{'message':{'content':None,'reasoning_content':'Provider reasoning',
        'tool_calls':[{'id':'t','function':{'name':'data_get_recovery_summary','arguments':'{"days":7}'}}]}}]}, 'deepseek-flash')
    assert _assistant_tool_call_message(response)['reasoning_content'] == 'Provider reasoning'


async def test_repeated_reads_execute_once_and_close_with_verified_results(db_session, monkeypatch):
    chat = AiChatSession(user_id=1,started_at=datetime.now(UTC),last_activity_at=datetime.now(UTC))
    db_session.add(chat); await db_session.commit()
    handler = AsyncMock(return_value={'data':{},'evidence_refs':[]})
    monkeypatch.setattr(TOOL_REGISTRY['data_get_recovery_summary'],'handler',handler)
    call = lambda ident: LLMResponse(content=None,model='fixture',tool_calls=[ToolCallRequest(ident,'data_get_recovery_summary',{'days':7})])
    llm = FixtureAgentLLMClient([call('one'),call('two'),LLMResponse(content='Recorded data is limited.',model='fixture')])
    result = await run_agent_loop(sessionmaker,llm,user_id=1,session_id=chat.id,text='Recovery?',system='Grounded',tier='cheap',today=date.today())
    assert result.reply == 'Recorded data is limited.'
    assert handler.await_count == 1
    assert len(llm.calls) == 3 and llm.calls[-1]['tools'] is None
    assert result.tool_audit[-1]['cached'] is True


async def test_recovery_summary_only_returns_owned_eligible_evidence(db_session):
    from app.models.user import User
    from app.services.evidence import record_observation
    other = User(name='Other recovery'); db_session.add(other); await db_session.flush()
    now = datetime.now(UTC)
    for uid, origin, source, value in [(1,'garmin','owned',52),(other.id,'garmin','other',90),(1,'strava','restricted',123)]:
        await record_observation(db_session,user_id=uid,metric='resting_hr',value=value,unit='bpm',origin=origin,
                                 source_record_id=source,measured_at=now,timezone='UTC',fetched_at=now)
    await db_session.flush()
    result = await TOOL_REGISTRY['data_get_recovery_summary'].handler(ToolContext(db_session,1,now.date()),days=7)
    values = [r['value'] for r in result['data']['resting_hr']['observations']]
    assert 52 in values and 90 not in values and 123 not in values
    assert result['data']['sleep_duration']['available'] is False
