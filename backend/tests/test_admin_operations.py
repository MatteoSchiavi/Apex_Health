"""Owner authorization, immutability, revocation and durable feedback."""
import uuid
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from app.models.admin import Feedback, OwnerNotification
from app.models.user import AuthCredential
from tests.test_invites import _owner_login, _mint
from tests.conftest import csrf_headers

async def friend(client, db_session):
    owner=await _owner_login(client,db_session)
    code=(await _mint(client,owner)).json()['code']
    email=f'admin-{uuid.uuid4().hex}@example.com'
    response=await client.post('/auth/invite/redeem',json={'code':code,'name':'Friend','email':email,'password':'strong-test-password'},headers=csrf_headers(client))
    assert response.status_code==201
    cookies=dict(response.cookies);uid=response.json()['user_id'];client.cookies.clear()
    return owner,cookies,uid,email

async def test_owner_admin_gate(client,db_session):
    assert (await client.get('/api/admin/users')).status_code==401
    owner,cookies,uid,email=await friend(client,db_session)
    for path in ('users','sessions','invites','feedback','notifications'):
        response=await client.get('/api/admin/'+path,cookies=cookies)
        assert response.status_code==403
        client.cookies.clear()
    response=await client.get('/api/admin/users?limit=1',cookies=owner)
    assert response.status_code==200
    assert len(response.json()['items'])==1

async def test_owner_immutable_and_friend_revocation(client,db_session):
    owner,cookies,uid,email=await friend(client,db_session)
    owner_id=await db_session.scalar(select(AuthCredential.user_id).where(AuthCredential.role=='owner').limit(1))
    response=await client.patch(f'/api/admin/users/{owner_id}',json={'disabled':True},cookies=owner,headers=csrf_headers(client,owner))
    assert response.status_code==409
    client.cookies.clear()
    response=await client.delete(f'/api/admin/users/{owner_id}/sessions',cookies=owner,headers=csrf_headers(client,owner))
    assert response.status_code==409
    client.cookies.clear()
    response=await client.patch(f'/api/admin/users/{uid}',json={'disabled':True},cookies=owner,headers=csrf_headers(client,owner))
    assert response.status_code==200
    client.cookies.clear()
    assert (await client.get('/api/admin/users',cookies=cookies)).status_code==401
    client.cookies.clear()
    response=await client.post('/auth/login',json={'email':email,'password':'strong-test-password'},headers=csrf_headers(client))
    assert response.status_code==401

async def test_feedback_durable_when_provider_fails(client,db_session,monkeypatch):
    owner,cookies,uid,email=await friend(client,db_session)
    from app.services import owner_notifications
    monkeypatch.setattr(owner_notifications,'configured',lambda:True)
    original_post=owner_notifications.httpx.AsyncClient.post
    async def fail_telegram(self,url,*args,**kwargs):
        if str(url).startswith('https://api.telegram.org/'):
            raise owner_notifications.httpx.ConnectError('offline')
        return await original_post(self,url,*args,**kwargs)
    monkeypatch.setattr(owner_notifications.httpx.AsyncClient,'post',fail_telegram)
    response=await client.post('/api/feedback',json={'category':'bug','message':'Something broke password=secret','page_url':'https://host/dashboard?token=secret#private'},cookies=cookies,headers=csrf_headers(client,cookies))
    assert response.status_code==201
    row=await db_session.get(Feedback,response.json()['id'])
    assert row.page_url=='/dashboard'
    assert 'secret' not in row.message
    outbox=await db_session.scalar(select(OwnerNotification).where(OwnerNotification.kind=='feedback',OwnerNotification.message.contains(f'#{row.id}')))
    assert outbox is not None
    assert outbox.delivered_at is None
    client.cookies.clear()
    response=await client.get('/api/admin/invites',cookies=owner)
    assert response.status_code==200
    assert all('code' not in item for item in response.json()['items'])

async def test_feedback_rate_and_validation(client,db_session):
    owner,cookies,uid,email=await friend(client,db_session)
    for i in range(5):
        response=await client.post('/api/feedback',json={'message':f'Issue {i}'},cookies=cookies,headers=csrf_headers(client,cookies))
        assert response.status_code==201
        client.cookies.clear()
    response=await client.post('/api/feedback',json={'message':'Sixth'},cookies=cookies,headers=csrf_headers(client,cookies))
    assert response.status_code==429

async def test_operational_log_allowlist_excludes_payloads(monkeypatch):
    import logging
    import json
    from app.core.logging import OperationalBufferHandler
    handler=OperationalBufferHandler()
    class Pipe:
        def lpush(self,key,value): self.value=value;return self
        def ltrim(self,*args): return self
        def expire(self,*args): return self
        def execute(self): return []
    pipe=Pipe()
    monkeypatch.setattr(handler.redis,'pipeline',lambda **kwargs:pipe)
    record=logging.LogRecord('connectors.garmin',logging.ERROR,__file__,1,'health password=secret token=private',(),None)
    handler.emit(record)
    row=json.loads(pipe.value)
    assert set(row)=={'id','timestamp','level','source','event'}
    assert 'secret' not in pipe.value and 'health' not in pipe.value
    record.error_code = 'ValueError'
    handler.emit(record)
    assert json.loads(pipe.value)['error_code'] == 'ValueError'
    record.error_code = 'private-token-and-health-payload'
    handler.emit(record)
    assert 'error_code' not in json.loads(pipe.value)

async def test_critical_events_transfer_deduplicates_durable_outbox(db_session,monkeypatch):
    import json
    from app.tasks import owner_notifications as tasks
    from app.core import redis as redis_module
    source='tasks.test_'+uuid.uuid4().hex
    events=[json.dumps({'id':uuid.uuid4().hex,'source':source,'event':'task_failed'}) for _ in range(2)]
    class Queue:
        def __init__(self): self.rows=list(events)
        async def lrange(self,*args): return list(self.rows)
        async def lrem(self,key,count,raw): self.rows.remove(raw)
        async def aclose(self): pass
    queue=Queue()
    monkeypatch.setattr(redis_module,'get_redis',lambda:queue)
    await tasks._collect_critical_events()
    assert not queue.rows
    # Replayed Redis entries after a crash must not create another durable row.
    queue.rows=list(events)
    await tasks._collect_critical_events()
    rows=(await db_session.scalars(select(OwnerNotification).where(OwnerNotification.kind=='system_error',OwnerNotification.message.contains(source)))).all()
    assert len(rows)==1
    assert rows[0].delivered_at is None

async def test_notification_retry_handles_malformed_body_and_delivery_idempotency(db_session,monkeypatch):
    from datetime import UTC,datetime,timedelta
    import httpx
    from app.services import owner_notifications as service
    notification=service.enqueue(db_session,'test','Safe operational test')
    await db_session.commit()
    monkeypatch.setattr(service,'configured',lambda:True)
    calls=[]
    bodies=[[],{'ok':True}]
    async def telegram_post(self,url,**kwargs):
        calls.append(kwargs['json'])
        return httpx.Response(200,json=bodies.pop(0),request=httpx.Request('POST',url))
    monkeypatch.setattr(service.httpx.AsyncClient,'post',telegram_post)
    assert await service.dispatch(db_session,notification_id=notification.id)==0
    assert notification.attempts==1 and notification.delivered_at is None
    assert notification.next_attempt_at>datetime.now(UTC)
    notification.next_attempt_at=datetime.now(UTC)-timedelta(seconds=1)
    await db_session.commit()
    assert await service.dispatch(db_session,notification_id=notification.id)==1
    assert await service.dispatch(db_session,notification_id=notification.id)==0
    assert notification.delivered_at is not None
    assert len(calls)==2

async def test_feedback_commit_survives_unexpected_dispatch_outage(client,db_session,monkeypatch):
    owner,cookies,uid,email=await friend(client,db_session)
    from app.services import owner_notifications as service
    monkeypatch.setattr(service,'dispatch',AsyncMock(side_effect=RuntimeError('unexpected outage')))
    response=await client.post('/api/feedback',json={'message':'Durable despite sender outage'},cookies=cookies,headers=csrf_headers(client,cookies))
    assert response.status_code==201
    assert response.json()['notification_status']=='pending'
    row=await db_session.get(Feedback,response.json()['id'])
    assert row.message=='Durable despite sender outage'
    notification=await db_session.scalar(select(OwnerNotification).where(OwnerNotification.feedback_id==row.id))
    assert notification is not None
    assert email in notification.message and 'Friend' in notification.message
    assert row.created_at.isoformat() in notification.message
