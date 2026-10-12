"""Deterministic education/comparison checks; no database fixtures needed."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Row
import pytest

from app.schemas.workouts import WorkoutStructure
from app.services.structured_workouts import education
from app.services.gear_comparison import comparison, eligible_record

AT = datetime(2026,10,12,12,tzinfo=UTC)


def activity(ident,days,**changes):
    return Row(**{'id':ident,'start_time':AT+timedelta(days=days),'discipline_id':1,
        'duration_s':3600,'distance_m':10000,'avg_hr':120,'avg_power':None,'data_completeness':'full',
        'weather_snapshot':None,'source_metrics':{'garmin':{'comparison_context':{
            'route_id':'loop','terrain':'paved','indoor':True,'time_convention':'elapsed','effort_type':'easy'}}},**changes})


def context(row,**changes):
    row.source_metrics['garmin']['comparison_context'].update(changes)
    return row


@pytest.mark.parametrize('locale',['en','it','it-IT'])
def test_education_recurses_repeat_children_and_preserves_prescription(locale):
    structure=WorkoutStructure(steps=[{'id':'warm','kind':'warmup','duration_s':600},
        {'id':'repeat','kind':'repeat','repetitions':4,'steps':[
            {'id':'work','kind':'interval','duration_s':120,'target':{'kind':'power_w','lower':180,'upper':200}},
            {'id':'rest','kind':'recovery','duration_s':60}]},
        {'id':'cool','kind':'cooldown','distance_m':500}])
    before=structure.model_dump()
    rows=education(structure,locale)
    assert [r['id'] for r in rows]==['warm','repeat','work','rest','cool']
    assert [r['number'] for r in rows]==['1','2','2.1','2.2','3']
    assert rows[2]['parent_id']=='repeat' and rows[2]['target']=={'kind':'power_w','lower':180,'upper':200}
    assert rows[3]['target'] is None and rows[3]['duration_s']==60
    assert rows[4]['distance_m']==500 and rows[1]['repetitions']==4
    assert len({r['common_mistake'] for r in rows})==5
    assert len({r['conservative_alternative'] for r in rows})==5
    assert structure.model_dump()==before
    assert ('Indicazioni generali' if locale.startswith('it') else 'Generic workout education') in rows[0]['limitation']


def test_education_strength_and_unknown_locale_remain_honest():
    rows=education(WorkoutStructure(steps=[{'id':'s','kind':'strength','exercise':'Squat','sets':3,'reps':5,'load_kg':40}]),'fr')
    assert rows[0]['exercise']=='Squat' and rows[0]['load_kg']==40
    assert rows[0]['target'] is None and rows[0]['duration_s'] is None
    assert rows[0]['execution'].startswith('Use controlled technique')


def test_equipment_pairs_are_one_to_one_scoped_measured_and_noncausal():
    result=comparison([activity(1,0),activity(2,-14)],
        [activity(3,-1,distance_m=9900),activity(4,-15,distance_m=9900)],'UTC')
    assert result['status']=='available' and len(result['pairs'])==2
    assert {(p['selected']['activity_id'],p['other']['activity_id']) for p in result['pairs']}=={(1,3),(2,4)}
    assert result['summaries'][0]['mean_speed_difference_pct']==pytest.approx(10000/9900*100-100)
    assert result['summaries'][0]['pair_count']==2
    assert result['units']['speed_m_s']=='m/s'
    assert 'descriptive_observations_not_causal_equipment_effect' in result['limitations']
    assert all(p['selected']['avg_power_w'] is None for p in result['pairs'])
    assert result['pairs'][0]['source_dependencies']


@pytest.mark.parametrize('changes',[
    {'discipline_id':None},{'distance_m':None},{'distance_m':float('nan')},
    {'duration_s':0},{'avg_hr':None},{'avg_hr':float('inf')},{'avg_hr':400},
    {'source_metrics':{}},{'source_metrics':[]},{'weather_snapshot':[]},{'data_completeness':'missing'},
])
def test_missing_or_invalid_inputs_never_become_comparison(changes):
    assert comparison([activity(1,0)],[activity(2,-1,**changes)],'UTC')['pairs']==[]


@pytest.mark.parametrize('changes',[
    {'route_id':'other'},{'terrain':'trail'},{'indoor':False},{'time_convention':'moving'},
    {'effort_type':'maximal'},{'route_id':''},{'terrain':''},{'route_id':{}},{'terrain':42},
])
def test_explicit_incompatible_or_missing_context_does_not_match(changes):
    assert comparison([activity(1,0)],[context(activity(2,-1),**changes)],'UTC')['pairs']==[]


@pytest.mark.parametrize('changes',[
    {'discipline_id':2},{'avg_hr':124},{'distance_m':12000},{'duration_s':5000},
    {'start_time':AT},{'start_time':AT-timedelta(days=91)},
])
def test_measurement_session_and_date_mismatches_do_not_match(changes):
    assert comparison([activity(1,0)],[activity(2,-1,**changes)],'UTC')['pairs']==[]


def test_shared_activity_excluded_and_single_pair_not_aggregated():
    shared=activity(1,0)
    result=comparison([shared,activity(2,-7)],[shared,activity(3,-8)],'UTC')
    assert result['shared_activity_count']==1
    assert len(result['pairs'])==1 and result['summaries']==[]


def test_different_scopes_never_aggregate_into_equipment_score():
    result=comparison([activity(1,0),context(activity(2,-7),route_id='other')],
        [activity(3,-1),context(activity(4,-8),route_id='other')],'UTC')
    assert len(result['pairs'])==2 and result['summaries']==[]


def test_outdoor_weather_required_and_tolerances_apply():
    a=context(activity(1,0),indoor=False)
    b=context(activity(2,-1),indoor=False)
    assert comparison([a],[b],'UTC')['pairs']==[]
    a.weather_snapshot={'temperature_c':20,'relative_humidity':50,'wind_speed_kmh':10}
    b.weather_snapshot={'temperature_c':23,'relative_humidity':60,'wind_speed_kmh':15}
    assert len(comparison([a],[b],'UTC')['pairs'])==1
    b.weather_snapshot['temperature_c']=23.1
    assert comparison([a],[b],'UTC')['pairs']==[]


def test_moving_time_requires_matching_source_measurement():
    a=context(activity(1,0),time_convention='moving')
    a.source_metrics['other']={'moving_time_s':3400}
    assert eligible_record(a,'UTC') is None
    a.source_metrics['garmin']['moving_time_s']=3400
    assert eligible_record(a,'UTC')['time_s']==3400
    a.source_metrics['garmin']['moving_time_s']=4000
    assert eligible_record(a,'UTC') is None


def test_asserted_context_keeps_actual_moving_source_and_provenance():
    a=activity(1,0)
    recorded=a.source_metrics['garmin'].pop('comparison_context')
    recorded['time_convention']='moving'
    a.source_metrics['garmin']['moving_time_s']=3400
    a.source_metrics['user_asserted:garmin']={'comparison_context':recorded}
    result=eligible_record(a,'UTC')
    assert result['time_s']==3400
    assert result['context'][0]=='user_asserted:garmin'
    assert any('user_asserted:garmin' in dep for dep in result['dependencies'])


def test_implausible_weather_is_not_compatible_evidence():
    a=context(activity(1,0),indoor=False)
    b=context(activity(2,-1),indoor=False)
    a.weather_snapshot=b.weather_snapshot={'temperature_c':20,'relative_humidity':150,'wind_speed_kmh':10}
    assert comparison([a],[b],'UTC')['pairs']==[]
