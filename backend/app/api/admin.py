"""Owner-only account and operational administration. Never returns health data."""
from typing import Literal
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import require_owner
from app.auth.invites import create_invite, revoke_invite, InviteError
from app.core.db import get_session
from app.core.redis import get_redis_dependency
from app.models.user import AuthCredential, User, UserSession, Invite
from app.models.admin import Feedback, OwnerNotification
from app.services.owner_notifications import configured, enqueue, dispatch
from app.services.admin_monitoring import system_metrics, read_logs
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_owner)])

async def page(session, model, fields, limit, offset, where=None):
    query = select(model)
    count = select(func.count()).select_from(model)
    if where is not None:
        query = query.where(where); count = count.where(where)
    rows = (await session.scalars(query.order_by(model.id.desc()).limit(limit).offset(offset))).all()
    return {"items": [{key:getattr(row,key) for key in fields} for row in rows], "total":await session.scalar(count),"limit":limit,"offset":offset}

@router.get("/users")
async def users(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=100000),session:AsyncSession=Depends(get_session)):
    rows=(await session.execute(select(User,AuthCredential).join(AuthCredential, User.id==AuthCredential.user_id).order_by(User.id.desc()).limit(limit).offset(offset))).all()
    now=datetime.now(UTC)
    active_counts=dict((await session.execute(select(UserSession.user_id,func.count()).where(UserSession.user_id.in_([u.id for u,c in rows]),UserSession.expires_at>now,(UserSession.absolute_expires_at.is_(None))|(UserSession.absolute_expires_at>now)).group_by(UserSession.user_id))).all())
    return {"items":[{"active_sessions":active_counts.get(u.id,0),"id":u.id,"name":u.name,"email":c.email,"role":c.role,"ai_access_tier":c.ai_access_tier,"share_segments":c.share_segments,"disabled":c.disabled,"last_login_at":c.last_login_at,"created_at":u.created_at} for u,c in rows],"total":await session.scalar(select(func.count()).select_from(AuthCredential)),"limit":limit,"offset":offset}

class PermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_access_tier: Literal['cheap_only','full'] | None = None
    disabled: bool | None = None
    share_segments: bool | None = None

async def mutable_user(session,user_id):
    cred=await session.scalar(select(AuthCredential).where(AuthCredential.user_id==user_id).with_for_update())
    if cred is None: raise HTTPException(404,"User not found")
    if cred.role=='owner': raise HTTPException(409,"Owner permissions and sessions cannot be revoked here")
    return cred

@router.patch('/users/{user_id}')
async def permissions(user_id:int,payload:PermissionUpdate,session:AsyncSession=Depends(get_session)):
    cred=await mutable_user(session,user_id)
    for key,value in payload.model_dump(exclude_none=True).items(): setattr(cred,key,value)
    if cred.disabled: await session.execute(delete(UserSession).where(UserSession.user_id==user_id))
    await session.commit()
    return {"updated":True}

@router.get('/sessions')
async def sessions(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=100000),user_id:int|None=None,session:AsyncSession=Depends(get_session)):
    result=await page(session,UserSession,['id','user_id','created_at','expires_at','absolute_expires_at','remember_me'],limit,offset,UserSession.user_id==user_id if user_id is not None else None)
    now=datetime.now(UTC)
    for item in result['items']:
        item['active']=item['expires_at']>now and (item['absolute_expires_at'] is None or item['absolute_expires_at']>now)
    return result

@router.delete('/sessions/{session_id}',status_code=204)
async def revoke_session(session_id:int,session:AsyncSession=Depends(get_session)):
    row=await session.get(UserSession,session_id)
    if row is None: raise HTTPException(404,'Session not found')
    await mutable_user(session,row.user_id)
    await session.delete(row); await session.commit()

@router.delete('/users/{user_id}/sessions',status_code=204)
async def revoke_sessions(user_id:int,session:AsyncSession=Depends(get_session)):
    await mutable_user(session,user_id)
    await session.execute(delete(UserSession).where(UserSession.user_id==user_id));await session.commit()

@router.get('/invites')
async def invites(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=100000),session:AsyncSession=Depends(get_session)):
    return await page(session,Invite,['id','created_by','used_by','expires_at','created_at'],limit,offset)

class InviteIn(BaseModel):
    expires_in_days:int=Field(7,ge=1,le=30)

@router.post('/invites',status_code=201)
async def invite(payload:InviteIn,owner:AuthCredential=Depends(require_owner),session:AsyncSession=Depends(get_session)):
    row=await create_invite(session,owner.user_id,payload.expires_in_days)
    return {'id':row.id,'code':row.code,'expires_at':row.expires_at}

@router.delete('/invites/{invite_id}',status_code=204)
async def revoke(invite_id:int,owner:AuthCredential=Depends(require_owner),session:AsyncSession=Depends(get_session)):
    try: found=await revoke_invite(session,invite_id,owner.user_id)
    except InviteError: raise HTTPException(409,'Invite already redeemed')
    if not found: raise HTTPException(404,'Invite not found')

@router.get('/feedback')
async def feedback(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=100000),session:AsyncSession=Depends(get_session)):
    result=await page(session,Feedback,['id','user_id','category','message','page_url','created_at'],limit,offset)
    notifications=(await session.scalars(select(OwnerNotification).where(OwnerNotification.feedback_id.in_([item['id'] for item in result['items']])))).all()
    statuses={row.feedback_id:('delivered' if row.delivered_at else 'retrying' if row.attempts else 'pending') for row in notifications}
    for item in result['items']: item['notification_status']=statuses.get(item['id'],'pending')
    return result

@router.get('/system')
async def system(session:AsyncSession=Depends(get_session)):
    return await system_metrics(session)

@router.get('/logs')
async def logs(limit:int=Query(100,ge=1,le=200),level:Literal['DEBUG','INFO','WARNING','ERROR','CRITICAL']|None=None,source:str|None=Query(None,max_length=80),redis=Depends(get_redis_dependency)):
    return {'items':await read_logs(redis,limit,level,source)}

@router.get('/notifications')
async def notifications(session:AsyncSession=Depends(get_session)):
    pending=await session.scalar(select(func.count()).select_from(OwnerNotification).where(OwnerNotification.delivered_at.is_(None)))
    failed=await session.scalar(select(func.count()).select_from(OwnerNotification).where(OwnerNotification.delivered_at.is_(None),OwnerNotification.attempts>0))
    return {'configured':configured(),'pending':pending,'failed':failed}

@router.post('/notifications/test')
async def notification_test(session:AsyncSession=Depends(get_session)):
    await session.execute(text('SELECT pg_advisory_xact_lock(73150423)'))
    latest=await session.scalar(select(OwnerNotification.created_at).where(OwnerNotification.kind=='test').order_by(OwnerNotification.id.desc()).limit(1))
    if latest and (datetime.now(UTC)-latest).total_seconds()<60: raise HTTPException(429,'Wait before sending another test')
    notification=enqueue(session,'test','Apex Health owner operational notification test')
    await session.commit();await dispatch(session,limit=1,notification_id=notification.id)
    return {'queued':True}
