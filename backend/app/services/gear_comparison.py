"""Descriptive equipment history, using owned canonical associations and explicit context.

Eligibility cutoffs limit mismatched recordings; they are not physiological thresholds.
No observed difference identifies an effect caused by equipment.
"""
from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.services.endurance_metrics import positive
from app.services.sport_progress import comparable_context

ACTIVITY_LIMIT = 500
MIN_PAIRS = 2


def eligible_record(activity, timezone):
    if not isinstance(activity.source_metrics, dict) or (activity.weather_snapshot is not None and not isinstance(activity.weather_snapshot, dict)):
        return None
    context = comparable_context(activity)
    distance, duration, hr = positive(activity.distance_m), positive(activity.duration_s), positive(activity.avg_hr)
    if (activity.discipline_id is None or not context or not distance or not duration
            or not hr or hr > 300 or activity.data_completeness not in {'full', 'partial'}):
        return None
    provider, scope, effort, environment = context
    # A route/terrain identity must be recorded, not an empty placeholder.
    source_context = activity.source_metrics[provider]['comparison_context']
    if any(not isinstance(source_context.get(key),str) or not source_context[key].strip() for key in ('route_id','terrain')):
        return None
    if scope[2] == 'False':
        temperature, humidity, wind = environment
        if not (-90 <= temperature <= 60 and 0 <= humidity <= 100 and 0 <= wind <= 300):
            return None
    dependency = f'activity:{activity.id}:duration_s'
    if scope[-1] == 'moving':
        # Keep moving-time measurements in the same source as the explicit context.
        actual_source = provider.removeprefix('user_asserted:')
        block = (activity.source_metrics or {}).get(actual_source)
        if not isinstance(block, dict):
            return None
        recorded = next(((key,value) for key in ('moving_time_s', 'total_moving_time')
            if (value := positive(block.get(key))) and value <= positive(activity.duration_s)), None)
        if recorded is None:
            return None
        key, duration = recorded
        dependency = f'activity:{activity.id}:source_metrics.{actual_source}.{key}'
    speed = distance / duration
    if speed > 100:
        return None
    power = positive(activity.avg_power, zero=True)
    if power is not None and power > 5000:
        power = None
    return {'activity':activity, 'context':context, 'date':activity.start_time.astimezone(ZoneInfo(timezone)).date().isoformat(),
        'distance_m':distance, 'time_s':duration, 'speed_m_s':speed, 'avg_hr_bpm':hr, 'avg_power_w':power,
        'dependencies':[f'activity:{activity.id}:distance_m', dependency, f'activity:{activity.id}:avg_hr',
            f'activity:{activity.id}:source_metrics.{provider}.comparison_context', f'activity:{activity.id}:weather_snapshot']}


def compatible(a, b):
    left, right = a['activity'], b['activity']
    if (left.id == right.id or left.discipline_id != right.discipline_id or a['date'] == b['date']
            or abs(left.start_time-right.start_time) > timedelta(days=90)
            or a['context'][:3] != b['context'][:3]
            or abs(a['avg_hr_bpm']-b['avg_hr_bpm']) > 3
            or not .9 <= a['distance_m']/b['distance_m'] <= 1.1
            or not .9 <= a['time_s']/b['time_s'] <= 1.1):
        return False
    indoor = a['context'][1][2] == 'True'
    return indoor or all(abs(x-y) <= tolerance for x,y,tolerance in
        zip(a['context'][3],b['context'][3],(3,10,5)))


def comparison(left_rows, right_rows, timezone):
    shared = {a.id for a in left_rows} & {a.id for a in right_rows}
    left = [value for a in left_rows if a.id not in shared and (value := eligible_record(a, timezone))]
    right = [value for a in right_rows if a.id not in shared and (value := eligible_record(a, timezone))]
    pairs, used = [], set()
    # Newest selected-gear sessions, nearest-date eligible counterpart, no activity reused.
    for a in sorted(left, key=lambda r:(r['activity'].start_time,r['activity'].id), reverse=True):
        candidates = [b for b in right if b['activity'].id not in used and compatible(a,b)]
        if not candidates:
            continue
        b = min(candidates,key=lambda r:(abs(r['activity'].start_time-a['activity'].start_time),r['activity'].id))
        used.add(b['activity'].id)
        def measured(r):
            return {key:r[key] for key in ('date','distance_m','time_s','speed_m_s','avg_hr_bpm','avg_power_w')} | {'activity_id':r['activity'].id}
        pairs.append({'selected':measured(a), 'other':measured(b), 'discipline_id':a['activity'].discipline_id,
            'context':{'source':a['context'][0], 'route_id':a['context'][1][0], 'terrain':a['context'][1][1],
                'indoor':a['context'][1][2]=='True','time_convention':a['context'][1][3], 'effort_type':a['context'][2]},
            'speed_difference_pct':(a['speed_m_s']/b['speed_m_s']-1)*100,
            'source_dependencies':a['dependencies']+b['dependencies']})
    # Never average different disciplines/routes/providers into an equipment score.
    scopes = Counter((p['discipline_id'],p['context']['source'],p['context']['route_id'],p['context']['terrain'],
        p['context']['indoor'],p['context']['time_convention'],p['context']['effort_type']) for p in pairs)
    return {'status':'available' if pairs else 'unavailable', 'reason':None if pairs else 'insufficient_compatible_recordings',
        'pairs':pairs, 'eligible_counts':{'selected':len(left),'other':len(right)},
        'shared_activity_count':len(shared), 'minimum_pairs_for_summary':MIN_PAIRS,
        'summaries':[{'discipline_id':key[0], 'source':key[1], 'route_id':key[2], 'terrain':key[3],
            'indoor':key[4], 'time_convention':key[5], 'effort_type':key[6], 'pair_count':count,
            'mean_speed_difference_pct':sum(p['speed_difference_pct'] for p in pairs if
                (p['discipline_id'],p['context']['source'],p['context']['route_id'],p['context']['terrain'],
                 p['context']['indoor'],p['context']['time_convention'],p['context']['effort_type'])==key)/count}
            for key,count in scopes.items() if count >= MIN_PAIRS],
        'units':{'distance_m':'m','time_s':'s','speed_m_s':'m/s','avg_hr_bpm':'bpm','avg_power_w':'W','speed_difference_pct':'%'},
        'method':'Newest selected-gear activity matched once to nearest-date compatible other-gear activity; (selected speed / other speed - 1) * 100. Scope summaries require two pairs and never combine disciplines or contexts.',
        'prerequisites':['same_equipment_type','same_recorded_discipline_provider_route_terrain_indoor_time_and_easy_or_steady_effort',
            'positive_distance_and_explicit_time_convention','recorded_average_HR_within_3_bpm','different_local_dates_within_90_days',
            'distance_and_duration_ratios_0.9_to_1.1','outdoor_temperature_within_3C_humidity_10pp_wind_5kmh'],
        'limitations':['descriptive_observations_not_causal_equipment_effect','fitness_fatigue_session_intent_and_sensor_differences_remain_confounders',
            'route_and_effort_context_may_be_user_asserted','whole_session_averages_not_verified_steady_streams',
            'same_activity_linked_to_both_equipment_excluded','eligibility_cutoffs_not_physiological_thresholds',
            'latest_500_linked_activities_per_equipment_only']}
