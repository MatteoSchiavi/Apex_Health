"""One review boundary for structured steps; deterministic education needs no AI."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from fastapi import HTTPException
from app.core.encryption import encrypt_bytes, decrypt_bytes
from app.models.activity import Discipline
from app.models.athlete_training import ActivityPlanLink, SessionCheckin
from app.models.lab import ChangeAudit
from app.models.structured_workout import StructuredWorkoutDraft, StructuredWorkoutVersion
from app.models.training import TrainingPlan, PlannedSession
from app.schemas.workouts import WorkoutStructure, total_seconds
from app.services.evidence import canonical, digest, scope_lock
from app.services.replanning import enforce_session_constraints

EDUCATION = {
 'en': {
  'warmup':('Prepare for the main work','Start gently and increase gradually; stop if you feel unwell.'),
  'easy':('Build consistent training','Keep effort comfortable. Reduce effort when fatigue or conditions change.'),
  'endurance':('Practice sustained effort','Use the prescribed range only when one is recorded; avoid chasing unsupported zones.'),
  'tempo':('Practice a sustained controlled effort','Start conservatively and keep the recorded target; do not turn every session into a test.'),
  'threshold':('Practice a demanding controlled effort','Use only your recorded prescription; shorten or replace with easy work if recovery is poor.'),
  'interval':('Practice repeated efforts','Follow each effort and recovery block. Pace the early repetitions and stop for concerning symptoms.'),
  'recovery':('Recover between efforts','Keep this block genuinely easy; use the explicit duration or distance if present.'),
  'cooldown':('Finish gradually','Reduce effort and allow a comfortable transition back to rest.'),
  'strength':('Practice the specified exercise','Use controlled technique and the entered sets/reps/load; avoid maximal effort when unwell.'),
  'technical':('Practice movement skills','Prioritize control and safe conditions over speed or load.'),
  'repeat':('Repeat a complete group','Complete the effort and recovery sequence in order for the recorded number of repetitions.'),
 },
 'it': {
  'warmup':('Preparati al lavoro principale','Inizia con calma e aumenta gradualmente; fermati se non ti senti bene.'),
  'easy':('Allenati con continuità','Mantieni uno sforzo comodo. Riducilo se cambiano fatica o condizioni.'),
  'endurance':('Pratica uno sforzo prolungato','Usa soltanto gli obiettivi registrati, senza inseguire zone non definite.'),
  'tempo':('Pratica uno sforzo controllato','Parti con prudenza e rispetta l’obiettivo registrato; non trasformare ogni seduta in un test.'),
  'threshold':('Pratica uno sforzo impegnativo controllato','Usa la prescrizione registrata; accorcia o scegli lavoro facile se recuperi poco.'),
  'interval':('Pratica sforzi ripetuti','Segui lavoro e recupero. Parti con prudenza e fermati in presenza di sintomi preoccupanti.'),
  'recovery':('Recupera tra gli sforzi','Mantieni questo blocco facile; usa durata o distanza esplicite, quando presenti.'),
  'cooldown':('Concludi gradualmente','Riduci lo sforzo e torna con calma al riposo.'),
  'strength':('Pratica l’esercizio indicato','Usa una tecnica controllata e serie, ripetizioni e carico inseriti; evita massimali se stai male.'),
  'technical':('Pratica abilità motorie','Dai priorità a controllo e condizioni sicure rispetto a velocità o carico.'),
  'repeat':('Ripeti un gruppo completo','Segui nell’ordine lavoro e recupero per il numero di ripetizioni registrato.'),
 }
}


# These are block-specific general options, not edits to the saved prescription.
EDUCATION_OPTIONS = {
    'en': {
        'warmup': ('Starting at main-work intensity or skipping preparation.', 'Start more gently and allow a gradual preparation; defer hard work if you remain unwell.'),
        'easy': ('Turning comfortable work into a hard test.', 'Slow down or shorten this block when comfort or recovery deteriorates.'),
        'endurance': ('Chasing an unrecorded zone or extending the block despite fatigue.', 'Use a shorter comfortable block; review any change to the recorded prescription.'),
        'tempo': ('Starting too fast and losing control before the block ends.', 'Reduce effort or replace demanding work with comfortable work when recovery is poor.'),
        'threshold': ('Treating the label as a measured physiological threshold or forcing the target.', 'Shorten the demanding block or choose easy work; the label alone does not define your threshold.'),
        'interval': ('Racing early repetitions or skipping the following recovery.', 'Reduce the effort or number of repetitions; keep the recovery sequence.'),
        'recovery': ('Keeping the effort high or omitting the prescribed recovery.', 'Make this block easier; allow more recovery rather than forcing the next effort.'),
        'cooldown': ('Finishing with another hard effort or stopping abruptly while uncomfortable.', 'Reduce effort gently and use a comfortable transition; stop for concerning symptoms.'),
        'strength': ('Adding load or repetitions when technique is deteriorating.', 'Reduce load or repetitions, or pause the exercise when controlled movement is no longer possible.'),
        'technical': ('Prioritizing speed or load over movement control.', 'Simplify the drill and practice slowly in safe conditions.'),
        'repeat': ('Repeating only the effort and omitting child recovery blocks.', 'Review fewer complete repetitions rather than removing recovery; keep child blocks in order.'),
    },
    'it': {
        'warmup': ('Partire subito all’intensità del lavoro principale o saltare la preparazione.', 'Inizia più piano e preparati gradualmente; rimanda il lavoro intenso se continui a stare male.'),
        'easy': ('Trasformare il lavoro comodo in un test impegnativo.', 'Rallenta o accorcia il blocco se peggiorano comfort o recupero.'),
        'endurance': ('Inseguire una zona non registrata o prolungare il blocco nonostante la fatica.', 'Scegli un blocco più breve e comodo; rivedi ogni modifica alla prescrizione registrata.'),
        'tempo': ('Partire troppo forte e perdere il controllo prima della fine del blocco.', 'Riduci lo sforzo o sostituisci il lavoro impegnativo con lavoro comodo se recuperi poco.'),
        'threshold': ('Considerare l’etichetta una soglia fisiologica misurata o forzare l’obiettivo.', 'Accorcia il blocco impegnativo o scegli lavoro facile; l’etichetta da sola non definisce la tua soglia.'),
        'interval': ('Gareggiare nelle prime ripetizioni o saltare il recupero successivo.', 'Riduci lo sforzo o il numero di ripetizioni; mantieni la sequenza dei recuperi.'),
        'recovery': ('Mantenere uno sforzo elevato o saltare il recupero prescritto.', 'Rendi il blocco più facile; concediti più recupero senza forzare lo sforzo successivo.'),
        'cooldown': ('Concludere con altro lavoro intenso o fermarsi bruscamente mentre si è a disagio.', 'Riduci lo sforzo gradualmente e torna con calma al riposo; fermati per sintomi preoccupanti.'),
        'strength': ('Aumentare carico o ripetizioni quando la tecnica peggiora.', 'Riduci carico o ripetizioni, oppure interrompi l’esercizio se perdi il controllo del movimento.'),
        'technical': ('Dare priorità a velocità o carico rispetto al controllo del movimento.', 'Semplifica l’esercizio e praticalo lentamente in condizioni sicure.'),
        'repeat': ('Ripetere solo lo sforzo saltando i blocchi di recupero interni.', 'Rivedi un numero minore di ripetizioni complete senza togliere i recuperi; mantieni l’ordine dei blocchi.'),
    },
}


def structure_of(row):
    return WorkoutStructure.model_validate_json(decrypt_bytes(row.structure_ciphertext))


def receipt(row):
    structure = structure_of(row)
    return {'id':row.id,'planned_session_id':row.planned_session_id,
        'revision':row.revision,'payload_hash':row.payload_hash,'source':row.source,
        'structure':structure.model_dump(mode='json'),'duration_total_s':total_seconds(structure.steps),'created_at':row.created_at}


def draft_out(row):
    structure = structure_of(row)
    return {'id':row.id,'planned_session_id':row.planned_session_id,'plan_revision':row.plan_revision,
        'workout_revision':row.workout_revision,'payload_hash':row.payload_hash,'status':row.status,
        'structure':structure.model_dump(mode='json'),'duration_total_s':total_seconds(structure.steps),'version_id':row.version_id}


async def owned(session,user_id,ident):
    result = (await session.execute(select(PlannedSession,TrainingPlan).join(TrainingPlan).where(
        PlannedSession.id==ident,TrainingPlan.user_id==user_id))).first()
    if not result:
        raise HTTPException(404,'Planned session not found')
    return result


async def latest(session,user_id,ident):
    return await session.scalar(select(StructuredWorkoutVersion).where(
        StructuredWorkoutVersion.user_id==user_id,StructuredWorkoutVersion.planned_session_id==ident)
        .order_by(StructuredWorkoutVersion.revision.desc()).limit(1))


async def edit_block_reason(session,user_id,workout,plan):
    from app.models.user import User
    user = await session.get(User,user_id)
    if workout.date < datetime.now(ZoneInfo(user.timezone)).date():
        return 'past'
    if workout.protected or plan.protected:
        return 'protected'
    recorded = await session.scalar(select(ActivityPlanLink.activity_id).where(
        ActivityPlanLink.user_id==user_id,ActivityPlanLink.planned_session_id==workout.id))
    finished = await session.scalar(select(SessionCheckin.id).where(SessionCheckin.user_id==user_id,
        SessionCheckin.planned_session_id==workout.id,SessionCheckin.status.in_(('completed','skipped'))))
    if recorded or finished:
        return 'recorded' if recorded else 'completed_or_skipped'
    return None


async def editable(session,user_id,workout,plan):
    reason = await edit_block_reason(session,user_id,workout,plan)
    if reason:
        raise HTTPException(409, {'past':'Past workouts remain historical records',
            'protected':'Protected workouts remain unchanged; remove protection explicitly before proposing edits',
            'recorded':'Recorded workouts remain historical records',
            'completed_or_skipped':'Completed and skipped workouts remain historical records'}[reason])


async def create_draft(session,user,payload,ident):
    await scope_lock(session,user.id,'changes')
    workout,plan = await owned(session,user.id,ident)
    current = await latest(session,user.id,ident)
    revision = current.revision if current else 0
    if plan.revision!=payload.expected_plan_revision or revision!=payload.expected_workout_revision:
        raise HTTPException(409,'Workout or plan changed; reload the review')
    await editable(session,user.id,workout,plan)
    data = payload.structure.model_dump(mode='json')
    fingerprint = digest([user.id,ident,plan.revision,revision,data])
    existing = await session.scalar(select(StructuredWorkoutDraft).where(
        StructuredWorkoutDraft.user_id==user.id,StructuredWorkoutDraft.planned_session_id==ident,
        StructuredWorkoutDraft.status=='draft')
        .order_by(StructuredWorkoutDraft.id.desc()).limit(1))
    if existing and existing.payload_hash==fingerprint:
        return draft_out(existing)
    row = StructuredWorkoutDraft(user_id=user.id,planned_session_id=ident,plan_revision=plan.revision,
        workout_revision=revision,structure_ciphertext=encrypt_bytes(canonical(data).encode()),payload_hash=fingerprint)
    session.add(row)
    await session.commit()
    return draft_out(row)


async def confirm(session,user,ident,payload):
    await scope_lock(session,user.id,'changes')
    row = await session.scalar(select(StructuredWorkoutDraft).where(
        StructuredWorkoutDraft.id==ident,StructuredWorkoutDraft.user_id==user.id))
    if not row:
        raise HTTPException(404,'Workout draft not found')
    if row.payload_hash!=payload.payload_hash:
        raise HTTPException(409,'Approval must match the displayed workout')
    if row.status=='confirmed':
        version = await session.get(StructuredWorkoutVersion,row.version_id)
        return receipt(version)
    newest = await session.scalar(select(StructuredWorkoutDraft.id).where(
        StructuredWorkoutDraft.user_id==user.id,StructuredWorkoutDraft.planned_session_id==row.planned_session_id,
        StructuredWorkoutDraft.status=='draft').order_by(StructuredWorkoutDraft.id.desc()).limit(1))
    if newest != row.id:
        raise HTTPException(409,'A newer workout review exists; review its current version')
    workout,plan = await owned(session,user.id,row.planned_session_id)
    current = await latest(session,user.id,workout.id)
    if plan.revision!=row.plan_revision or (current.revision if current else 0)!=row.workout_revision:
        raise HTTPException(409,'Plan or workout changed since the displayed draft')
    await editable(session,user.id,workout,plan)
    structure = structure_of(row)
    seconds = total_seconds(structure.steps)
    duration = math.ceil(seconds/60) if seconds is not None else workout.target_duration_min
    after = {'target_id':workout.id,'date':str(workout.date),'session_type':workout.session_type,
             'target_duration_min':duration,'description':workout.description}
    await enforce_session_constraints(session,user.id,after)
    version = StructuredWorkoutVersion(user_id=user.id,planned_session_id=workout.id,revision=row.workout_revision+1,
        structure_ciphertext=row.structure_ciphertext,payload_hash=row.payload_hash,source='user_reviewed')
    session.add(version)
    await session.flush()
    workout.target_duration_min = duration
    plan.revision += 1
    row.status,row.version_id = 'confirmed',version.id
    session.add(ChangeAudit(user_id=user.id,action='workout_structure_confirmed',payload={
        'planned_session_id':workout.id,'workout_revision':version.revision,'draft_id':row.id,'payload_hash':row.payload_hash}))
    await session.commit()
    return receipt(version)


async def approved_plan_steps(session,user_id,workout,steps):
    """The plan's existing exact-hash confirmation also approves its explicit steps."""
    if not steps:
        return
    structure = WorkoutStructure(title=(workout.description or '')[:200],steps=steps)
    await session.flush()
    data = structure.model_dump(mode='json')
    session.add(StructuredWorkoutVersion(user_id=user_id,planned_session_id=workout.id,revision=1,
        structure_ciphertext=encrypt_bytes(canonical(data).encode()),payload_hash=digest([user_id,workout.id,data]),source='approved_plan'))


def education(structure,locale):
    language = 'it' if str(locale).lower().split('-')[0] == 'it' else 'en'
    catalog, options = EDUCATION[language], EDUCATION_OPTIONS[language]
    rows = []

    def visit(steps, parent_id=None, prefix=''):
        for index, step in enumerate(steps, 1):
            number = f'{prefix}{index}'
            rows.append({
                'id':step.id, 'kind':step.kind, 'number':number, 'parent_id':parent_id,
                'objective':catalog[step.kind][0], 'execution':catalog[step.kind][1],
                'target':step.target.model_dump(mode='json') if step.target else None,
                'duration_s':step.duration_s, 'distance_m':step.distance_m,
                'description':step.description, 'repetitions':step.repetitions,
                'exercise':step.exercise, 'sets':step.sets, 'reps':step.reps, 'load_kg':step.load_kg,
                'common_mistake':options[step.kind][0], 'conservative_alternative':options[step.kind][1],
                'limitation':('Indicazioni generali, senza previsioni mediche individuali. Le alternative non modificano il piano salvato.'
                    if language == 'it' else 'Generic workout education; no individualized medical prediction. Alternatives do not change the saved plan.'),
            })
            if step.steps:
                visit(step.steps, step.id, number+'.')

    visit(structure.steps)
    return rows
