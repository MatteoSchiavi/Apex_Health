"""Private owner management and bearer-header-only frozen public reads."""
from fastapi import APIRouter, Depends, Header, Request, Response, Query
from typing import Literal
from sqlalchemy import select
from app.models.activity import Activity, Discipline
from app.models.training import TrainingPlan, PlannedSession
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.schemas.sharing import SharePreviewIn, ShareCreateIn
from app.services import sharing

router = APIRouter(tags=['athlete-sharing'])


def private_response(response):
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Robots-Tag']='noindex, nofollow'


@router.post('/athlete/shares/preview')
async def preview(payload:SharePreviewIn,response:Response,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    private_response(response)
    result,_ = await sharing.preview(session,user,payload)
    return result


@router.post('/athlete/shares',status_code=201)
async def create(payload:ShareCreateIn,response:Response,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    private_response(response)
    return await sharing.create(session,user,payload)


@router.get('/athlete/shares')
async def shares(response:Response,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    private_response(response)
    return await sharing.list_owned(session,user.id)


@router.delete('/athlete/shares/{ident}',status_code=204)
async def revoke(ident:int,response:Response,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    private_response(response)
    await sharing.revoke(session,user.id,ident)


@router.get('/sharing/view')
async def read(request:Request,response:Response,x_apex_share:str|None=Header(default=None),session:AsyncSession=Depends(get_session)):
    private_response(response)
    if request.query_params:
        raise sharing.unavailable()
    return await sharing.read_public(session,x_apex_share)


@router.get('/athlete/shares/resources')
async def resources(type:Literal['activity','workout','plan'],response:Response,limit:int=Query(default=100,ge=1,le=100),
        offset:int=Query(default=0,ge=0,le=1000000),user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    private_response(response)
    if type=='activity':
        rows=(await session.execute(select(Activity,Discipline.name).outerjoin(Discipline,Discipline.id==Activity.discipline_id).where(Activity.user_id==user.id)
            .order_by(Activity.start_time.desc(),Activity.id.desc()).offset(offset).limit(limit))).all()
        items=[{'id':a.id,'date':a.local_date.isoformat(),'discipline':name,'duration_min':a.duration_s/60 if a.duration_s is not None else None} for a,name in rows]
    elif type=='workout':
        rows=(await session.execute(select(PlannedSession,Discipline.name).join(TrainingPlan,TrainingPlan.id==PlannedSession.training_plan_id).outerjoin(Discipline,Discipline.id==PlannedSession.discipline_id)
            .where(TrainingPlan.user_id==user.id,TrainingPlan.status.in_(sharing.APPROVED_PLANS))
            .order_by(PlannedSession.date.desc(),PlannedSession.id.desc()).offset(offset).limit(limit))).all()
        items=[{'id':a.id,'date':a.date.isoformat(),'discipline':name,'duration_min':a.target_duration_min,'title':a.session_type} for a,name in rows]
    else:
        rows=(await session.scalars(select(TrainingPlan).where(TrainingPlan.user_id==user.id,TrainingPlan.status.in_(sharing.APPROVED_PLANS))
            .order_by(TrainingPlan.week_start.desc(),TrainingPlan.id.desc()).offset(offset).limit(limit))).all()
        items=[{'id':a.id,'date':a.week_start.isoformat(),'title':a.title or 'Training plan'} for a in rows]
    return {'items':items,'offset':offset,'limit':limit,'has_more':len(items)==limit}
