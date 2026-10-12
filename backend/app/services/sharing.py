"""Owned canonical records -> exact encrypted review snapshot -> read capability."""
import hashlib
import json
import math
import re
import secrets
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from app.core.encryption import decrypt_bytes, encrypt_bytes
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.athlete import AthleteProfile
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.lab import ChangeAudit
from app.models.sharing import AthleteShare
from app.models.structured_workout import StructuredWorkoutVersion
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import AuthCredential
from app.schemas.sharing import FEEDBACK_FIELDS
from app.services.evidence import canonical, digest, scope_lock

VERSION = 'apex-athlete-sharing-v1'
PRIVACY_NOTICE = 'Anyone with the private link can view this exact snapshot until expiry or revocation. They may save a copy. Only the displayed fields are shared; there is no write or Coach access.'
SOURCES = {'garmin','fit','strava','whoop','oura','coros','technogym','csv_import','manual','apple_healthkit'}
APPROVED_PLANS = {'confirmed', 'active', 'completed'}
SNAPSHOT_BYTES = 256 * 1024
FEEDBACK_MAP = {'feedback_status':'status', 'rpe':'rpe', 'fatigue':'fatigue', 'soreness':'soreness',
    'workout_quality':'workout_quality', 'feedback_note':'note', 'modification_reason':'modification_reason', 'terrain_notes':'terrain_notes'}


def unavailable():
    return HTTPException(404, 'Shared view unavailable')


def number(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def add_dependency(dependencies, kind, ident):
    values = dependencies.setdefault(kind, [])
    if ident not in values:
        values.append(ident)


async def owner_enabled(session, user_id):
    credential = await session.get(AuthCredential, user_id, populate_existing=True)
    return credential is not None and not credential.disabled


async def owned_activities(session, user_id, ids):
    rows = (await session.scalars(select(Activity).where(Activity.user_id == user_id, Activity.id.in_(ids))
        .order_by(Activity.id).with_for_update())).all()
    if {row.id for row in rows} != set(ids):
        raise HTTPException(404, 'Selected activity not found')
    # Canonical summaries are shareable; unsupported provider payloads are not.
    sources = set((await session.scalars(select(ActivitySourceLink.source).where(
        ActivitySourceLink.user_id == user_id, ActivitySourceLink.activity_id.in_(ids)))).all())
    if not sources <= SOURCES:
        raise HTTPException(422, 'A selected activity has an unsupported source; it cannot be shared')
    return {row.id:row for row in rows}


async def owned_workouts(session, user_id, ids):
    rows = (await session.execute(select(PlannedSession, TrainingPlan).join(TrainingPlan).where(
        PlannedSession.id.in_(ids), TrainingPlan.user_id == user_id).order_by(PlannedSession.id)
        .with_for_update(of=(PlannedSession, TrainingPlan)))).all()
    if {row.id for row, _ in rows} != set(ids):
        raise HTTPException(404, 'Selected workout not found')
    if any(plan.status not in APPROVED_PLANS for _, plan in rows):
        raise HTTPException(409, 'Confirm the plan before sharing its workouts')
    return {row.id:(row, plan) for row, plan in rows}


async def discipline_names(session):
    return dict((await session.execute(select(Discipline.id, Discipline.name))).all())


async def feedback(session, user_id, fields, dependencies, *, activity=None, workout=None):
    chosen = [field for field in fields if field in FEEDBACK_FIELDS]
    if not chosen:
        return {}
    row = None
    if activity is not None:
        row = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user_id,
            SessionCheckin.activity_id == activity.id).order_by(SessionCheckin.id.desc()).limit(1))
        if row is None:
            link = await session.scalar(select(ActivityPlanLink).join(PlannedSession,
                PlannedSession.id == ActivityPlanLink.planned_session_id).join(TrainingPlan).where(
                ActivityPlanLink.user_id == user_id, ActivityPlanLink.activity_id == activity.id,
                ActivityPlanLink.method == 'user_confirmed', TrainingPlan.user_id == user_id))
            if link:
                row = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user_id,
                    SessionCheckin.planned_session_id == link.planned_session_id).order_by(SessionCheckin.id.desc()).limit(1))
                if row:
                    add_dependency(dependencies, 'association', link.activity_id)
                    add_dependency(dependencies, 'workout', link.planned_session_id)
    else:
        row = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user_id,
            SessionCheckin.planned_session_id == workout.id).order_by(SessionCheckin.id.desc()).limit(1))
        if row is None:
            link = await session.scalar(select(ActivityPlanLink).join(Activity, Activity.id == ActivityPlanLink.activity_id).where(
                ActivityPlanLink.user_id == user_id, Activity.user_id == user_id,
                ActivityPlanLink.planned_session_id == workout.id, ActivityPlanLink.method == 'user_confirmed'))
            if link:
                row = await session.scalar(select(SessionCheckin).where(SessionCheckin.user_id == user_id,
                    SessionCheckin.activity_id == link.activity_id).order_by(SessionCheckin.id.desc()).limit(1))
                if row:
                    await owned_activities(session, user_id, [link.activity_id])
                    add_dependency(dependencies, 'association', link.activity_id)
                    add_dependency(dependencies, 'activity', link.activity_id)
    if row:
        add_dependency(dependencies, 'checkin', row.id)
    return {field: getattr(row, FEEDBACK_MAP[field]) if row else None for field in chosen}


async def steps(session, user_id, workout, dependencies):
    from app.services.structured_workouts import structure_of
    row = await session.scalar(select(StructuredWorkoutVersion).where(StructuredWorkoutVersion.user_id == user_id,
        StructuredWorkoutVersion.planned_session_id == workout.id).order_by(StructuredWorkoutVersion.revision.desc()).limit(1))
    if row is None:
        return None
    add_dependency(dependencies, 'structured_workout', row.id)
    return structure_of(row).model_dump(mode='json')['steps']


async def workout_fields(session, user_id, workout, fields, names, dependencies):
    add_dependency(dependencies, 'workout', workout.id)
    values = {'date':workout.date.isoformat(), 'discipline':names.get(workout.discipline_id),
        'duration_min':workout.target_duration_min, 'distance_m':number(workout.target_distance_m),
        'session_type':workout.session_type, 'start_time':workout.start_time.isoformat() if workout.start_time else None,
        'description':workout.description or '', 'intensity_targets':{key:value for key,value in (workout.intensity_targets or {}).items()
            if key in {'hr_bpm','power_w','pace_s_km','rpe'} and isinstance(value,str) and len(value) <= 200}}
    result = {field:values[field] for field in fields if field in values}
    if 'steps' in fields:
        result['steps'] = await steps(session, user_id, workout, dependencies)
    result.update(await feedback(session, user_id, fields, dependencies, workout=workout))
    return result


def metric_snapshot(row, keys):
    value = row.get('value')
    return {'value': {key:number(value.get(key)) for key in keys} if isinstance(value,dict) else None,
        'unit':row.get('unit'), 'availability':row.get('availability'),
        'unavailable_reason':row.get('unavailable_reason'), 'formula':row.get('formula'),
        'formula_version':row.get('formula_version'), 'limitations':list(row.get('limitations') or [])}


async def progress_snapshot(session, user, selection, dependencies):
    from app.services.sport_progress import sport_overview, utc_bounds, SPORTS, ACTIVITY_LIMIT
    left, right = utc_bounds(selection.starts_on, selection.ends_on, user.timezone)
    ids = list((await session.scalars(select(Activity.id).join(Discipline).where(Activity.user_id == user.id,
        Discipline.name.in_(SPORTS[selection.sport]), Activity.start_time >= left, Activity.start_time < right)
        .order_by(Activity.id).limit(ACTIVITY_LIMIT + 1))).all())
    if len(ids) > ACTIVITY_LIMIT:
        raise HTTPException(422, 'Choose a shorter progress range with at most 10000 activities')
    if ids:
        await owned_activities(session, user.id, ids)
        dependencies['activity'] = ids
    overview = await sport_overview(session, user, selection.sport, selection.starts_on, selection.ends_on)
    fields = {}
    if 'volume' in selection.fields:
        totals = overview['totals']
        missing = any(totals.get(key) is None for key in ('duration_s', 'distance_m'))
        fields['volume'] = {'value':{key:totals.get(key) for key in ('activity_count','duration_s','distance_m')},
            'unit':{'activity_count':'count','duration_s':'s','distance_m':'m'},
            'availability':'partial' if missing or overview['quality'].get('activity_limit_reached') else 'available',
            'unavailable_reason':'some_selected_measurements_missing' if missing else None,
            'formula':totals['formula'], 'formula_version':totals['formula_version'],
            'limitations':['missing_measurements_not_zero','recorded_history_not_proof_of_no_training']}
    if 'consistency' in selection.fields:
        fields['consistency'] = metric_snapshot(overview['consistency'],
            ('active_weeks','observed_weeks','training_days','activity_count','active_week_pct'))
    if 'adherence' in selection.fields:
        fields['adherence'] = metric_snapshot(overview['adherence'],
            ('planned_count','completed_count','partial_count','skipped_count','unresolved_count','completion_pct'))
        workout_ids = list((await session.scalars(select(PlannedSession.id).join(TrainingPlan).join(Discipline,
            Discipline.id == PlannedSession.discipline_id).where(TrainingPlan.user_id == user.id,
            TrainingPlan.status.in_(APPROVED_PLANS), Discipline.name.in_(SPORTS[selection.sport]),
            PlannedSession.date >= selection.starts_on, PlannedSession.date <= selection.ends_on)
            .order_by(PlannedSession.id).limit(ACTIVITY_LIMIT+1))).all())
        if len(workout_ids) > ACTIVITY_LIMIT:
            raise HTTPException(422, 'Choose a shorter progress range with at most 10000 planned workouts')
        if workout_ids:
            dependencies['workout'] = workout_ids
        conditions = []
        if ids:
            conditions.append(SessionCheckin.activity_id.in_(ids))
        if workout_ids:
            conditions.append(SessionCheckin.planned_session_id.in_(workout_ids))
        if conditions:
            dependencies['checkin'] = list((await session.scalars(select(SessionCheckin.id).where(
                SessionCheckin.user_id == user.id, or_(*conditions)))).all())
        if ids:
            dependencies['association'] = list((await session.scalars(select(ActivityPlanLink.activity_id).where(
                ActivityPlanLink.user_id == user.id, ActivityPlanLink.activity_id.in_(ids),
                ActivityPlanLink.method == 'user_confirmed'))).all())
    if 'goal_progress' in selection.fields:
        fields['goal_progress'] = metric_snapshot(overview['goal_context']['goal_progress'], ())
        if await session.get(AthleteProfile, user.id):
            dependencies['profile'] = [user.id]
    return {'type':'progress', 'title':'Selected sport progress', 'sport':selection.sport,
        'range':{'starts_on':selection.starts_on.isoformat(),'ends_on':selection.ends_on.isoformat()}, 'fields':fields}


async def build_snapshot(session, user, selection):
    dependencies = {}
    if not await owner_enabled(session, user.id):
        raise HTTPException(403, 'Sharing is unavailable for this account')
    if selection.type == 'progress':
        snapshot = await progress_snapshot(session, user, selection, dependencies)
    else:
        names = await discipline_names(session)
        items = []
        if selection.type == 'activity':
            activities = await owned_activities(session, user.id, selection.resource_ids)
            for ident in selection.resource_ids:
                activity = activities[ident]
                add_dependency(dependencies, 'activity', ident)
                values = {'date':activity.start_time.astimezone(ZoneInfo(user.timezone)).date().isoformat(),
                    'discipline':names.get(activity.discipline_id), 'duration_s':activity.duration_s,
                    **{key:number(getattr(activity,key)) for key in ('distance_m','elevation_gain_m','avg_hr','max_hr','avg_power','np_power')}}
                selected = {field:values[field] for field in selection.fields if field in values}
                selected.update(await feedback(session, user.id, selection.fields, dependencies, activity=activity))
                items.append({'label':f'Activity {len(items)+1}', 'fields':selected})
        elif selection.type == 'workout':
            workouts = await owned_workouts(session, user.id, selection.resource_ids)
            for ident in selection.resource_ids:
                workout, plan = workouts[ident]
                add_dependency(dependencies, 'plan', plan.id)
                selected = await workout_fields(session, user.id, workout, selection.fields, names, dependencies)
                items.append({'label':f'Workout {len(items)+1}', 'fields':selected})
        else:
            plans = (await session.scalars(select(TrainingPlan).where(TrainingPlan.user_id == user.id,
                TrainingPlan.id.in_(selection.resource_ids)).order_by(TrainingPlan.id).with_for_update())).all()
            if {row.id for row in plans} != set(selection.resource_ids):
                raise HTTPException(404, 'Selected plan not found')
            by_id = {row.id:row for row in plans}
            for ident in selection.resource_ids:
                plan = by_id[ident]
                if plan.status not in APPROVED_PLANS:
                    raise HTTPException(409, 'Confirm the plan before sharing it')
                add_dependency(dependencies, 'plan', plan.id)
                workouts = (await session.scalars(select(PlannedSession).where(PlannedSession.training_plan_id == plan.id)
                    .order_by(PlannedSession.date,PlannedSession.id).limit(501))).all()
                if len(workouts) > 500:
                    raise HTTPException(422, 'Share selected workouts from this plan; it exceeds 500 sessions')
                values = {'title':plan.title or '', 'starts_on':plan.week_start.isoformat(),
                    'ends_on':plan.end_date.isoformat() if plan.end_date else None, 'session_count':len(workouts)}
                selected = {field:values[field] for field in selection.fields if field in values}
                fields = ['date','discipline','duration_min','distance_m'] if 'sessions' in selection.fields else []
                if 'session_instructions' in selection.fields:
                    fields.append('description')
                fields += [field for field in selection.fields if field in FEEDBACK_FIELDS or field in {'steps','intensity_targets'}]
                if fields:
                    selected['sessions'] = [await workout_fields(session,user.id,workout,fields,names,dependencies) for workout in workouts]
                elif 'session_count' in selection.fields:
                    for workout in workouts:
                        add_dependency(dependencies, 'workout', workout.id)
                items.append({'label':f'Plan {len(items)+1}', 'fields':selected})
        snapshot = {'type':selection.type, 'title':f'Selected {selection.type} summaries', 'items':items}
    snapshot['version'] = VERSION
    snapshot['rights'] = 'view'
    if len(canonical(snapshot).encode()) > SNAPSHOT_BYTES:
        raise HTTPException(422, 'The selected snapshot exceeds 256 KB; choose fewer records or fields')
    return snapshot, dependencies


async def preview(session, user, payload):
    await scope_lock(session, user.id, 'changes')
    snapshot, dependencies = await build_snapshot(session, user, payload.selection)
    content_hash = digest([VERSION,user.id,payload.selection.model_dump(mode='json'),payload.expires_in_days,snapshot])
    return {'snapshot':snapshot,'payload_hash':content_hash,'expires_in_days':payload.expires_in_days,
        'rights':'view','privacy_notice':PRIVACY_NOTICE}, dependencies


def metadata(row, now=None):
    now = now or datetime.now(UTC)
    state = 'revoked' if row.revoked_at else 'expired' if row.expires_at <= now else 'active'
    return {'id':row.id, **row.selection, 'rights':'view','created_at':row.created_at,
        'expires_at':row.expires_at,'revoked_at':row.revoked_at,'state':state}


async def create(session, user, payload):
    approved, dependencies = await preview(session,user,payload)
    if not secrets.compare_digest(approved['payload_hash'],payload.preview_hash):
        raise HTTPException(409,'Selected information changed; review a fresh sharing preview')
    active = await session.scalar(select(func.count()).select_from(AthleteShare).where(AthleteShare.user_id == user.id,
        AthleteShare.revoked_at.is_(None),AthleteShare.expires_at > datetime.now(UTC)))
    if active >= 100:
        raise HTTPException(422,'Revoke an existing share before creating more than 100 active links')
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    row = AthleteShare(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
        selection=payload.selection.model_dump(mode='json'), dependencies=dependencies,
        snapshot_ciphertext=encrypt_bytes(canonical(approved['snapshot']).encode()), payload_hash=approved['payload_hash'],
        created_at=now, expires_at=now+timedelta(days=payload.expires_in_days))
    session.add(row)
    await session.flush()
    session.add(ChangeAudit(user_id=user.id,action='athlete_share_created',payload={
        'share_id':row.id,'type':row.selection['type'],'fields':row.selection['fields'],
        'include_feedback':row.selection['include_feedback'],'expires_at':row.expires_at.isoformat(),'rights':'view'}))
    await session.commit()
    return {'grant':metadata(row),'snapshot':approved['snapshot'],'token':token,'url_fragment':'#'+token}


async def erase_expired(session, user_id):
    now = datetime.now(UTC)
    expired = (await session.scalars(select(AthleteShare).where(AthleteShare.user_id==user_id,
        AthleteShare.expires_at<=now,AthleteShare.snapshot_ciphertext.is_not(None)).with_for_update())).all()
    for row in expired:
        row.snapshot_ciphertext = None
        row.erased_at = now


async def list_owned(session, user_id):
    await scope_lock(session,user_id,'changes')
    await erase_expired(session,user_id)
    rows = (await session.scalars(select(AthleteShare).where(AthleteShare.user_id==user_id)
        .order_by(AthleteShare.id.desc()).limit(200))).all()
    await session.commit()
    return [metadata(row) for row in rows]


async def revoke(session,user_id,ident):
    await scope_lock(session,user_id,'changes')
    row = await session.scalar(select(AthleteShare).where(AthleteShare.id==ident,AthleteShare.user_id==user_id).with_for_update())
    if row is None:
        raise HTTPException(404,'Share not found')
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        row.snapshot_ciphertext = None
        row.erased_at = row.revoked_at
        session.add(ChangeAudit(user_id=user_id,action='athlete_share_revoked',payload={'share_id':row.id}))
    await session.commit()


async def dependencies_exist(session,user_id,dependencies):
    for kind,ids in dependencies.items():
        if kind=='workout':
            query = select(func.count()).select_from(PlannedSession).join(TrainingPlan).where(
                TrainingPlan.user_id==user_id,PlannedSession.id.in_(ids))
        else:
            models = {'activity':(Activity,Activity.id),'plan':(TrainingPlan,TrainingPlan.id),
                'checkin':(SessionCheckin,SessionCheckin.id),'association':(ActivityPlanLink,ActivityPlanLink.activity_id),
                'structured_workout':(StructuredWorkoutVersion,StructuredWorkoutVersion.id),'profile':(AthleteProfile,AthleteProfile.user_id)}
            if kind not in models:
                return False
            model, ident = models[kind]
            query = select(func.count()).select_from(model).where(model.user_id==user_id,ident.in_(ids))
        if await session.scalar(query) != len(ids):
            return False
        if kind == 'activity' and ids:
            sources = set((await session.scalars(select(ActivitySourceLink.source).where(
                ActivitySourceLink.user_id == user_id, ActivitySourceLink.activity_id.in_(ids)))).all())
            if not sources <= SOURCES:
                return False
    return True


async def read_public(session,token):
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
        raise unavailable()
    row = await session.scalar(select(AthleteShare).where(AthleteShare.token_hash==hashlib.sha256(token.encode()).hexdigest()).with_for_update())
    if row is None:
        raise unavailable()
    now = datetime.now(UTC)
    if row.revoked_at or row.expires_at<=now or not row.snapshot_ciphertext:
        if row.expires_at<=now and row.snapshot_ciphertext:
            row.snapshot_ciphertext=None
            row.erased_at=now
            await session.commit()
        raise unavailable()
    if not await owner_enabled(session,row.user_id) or not await dependencies_exist(session,row.user_id,row.dependencies):
        raise unavailable()
    snapshot = json.loads(decrypt_bytes(row.snapshot_ciphertext))
    return {'snapshot':snapshot,'expires_at':row.expires_at,'rights':'view'}


async def erase_unavailable(session,user_id):
    """Erasure flows remove retained snapshot bytes whose owned sources vanished."""
    rows = (await session.execute(select(AthleteShare.id,AthleteShare.dependencies).where(
        AthleteShare.user_id==user_id,AthleteShare.snapshot_ciphertext.is_not(None)))).all()
    now=datetime.now(UTC)
    for ident,dependencies in rows:
        if not await dependencies_exist(session,user_id,dependencies):
            row=await session.get(AthleteShare,ident)
            row.revoked_at=row.revoked_at or now
            row.snapshot_ciphertext=None
            row.erased_at=now
            session.add(ChangeAudit(user_id=user_id,action='athlete_share_source_erased',payload={'share_id':ident}))


async def revoke_for_activity_ids(session,user_id,activity_ids):
    """A merged surviving row must not retain erased-provider facts in a share."""
    if not activity_ids:
        return
    affected=set(activity_ids)
    rows=(await session.execute(select(AthleteShare.id,AthleteShare.dependencies).where(
        AthleteShare.user_id==user_id,AthleteShare.snapshot_ciphertext.is_not(None)))).all()
    now=datetime.now(UTC)
    for ident,dependencies in rows:
        if affected.intersection(dependencies.get('activity',[])):
            row=await session.get(AthleteShare,ident)
            row.revoked_at=row.revoked_at or now
            row.snapshot_ciphertext=None
            row.erased_at=now
            session.add(ChangeAudit(user_id=user_id,action='athlete_share_source_erased',payload={'share_id':ident}))
