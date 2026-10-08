"""Malformed model claims fail closed instead of crashing the answer boundary."""
import json
import pytest
from app.agent.loop import claim_examples, validate_answer


@pytest.mark.parametrize('field,value', [
    ('evidence_id', []), ('evidence_id', {}), ('metric', []), ('unit', {}),
    ('value', []), ('value', {}), ('value', float('nan')), ('value', float('inf')),
])
def test_malformed_claim_scalars_cannot_be_verified(field, value):
    claim = {'evidence_id': 'observation:1:1', 'metric': 'resting_hr', 'value': 50}
    claim[field] = value
    reply, receipt = validate_answer(json.dumps({'answer': 'Recorded resting HR is 50.', 'claims': [claim]}),
        [{'id': 'observation:1:1', 'metric': 'resting_hr', 'value': 50, 'unit': 'bpm'}])
    assert receipt['status'] == 'invalid'
    assert receipt['verified_claims'] == []
    assert '50' not in reply


@pytest.mark.parametrize('refs', [None, True, 1, 'analysis:1', [{}], [1]])
def test_malformed_evidence_refs_do_not_create_analysis_handles(refs):
    reply, receipt = validate_answer(json.dumps({'answer': 'No supported numerical result.', 'claims': []}),
        [{'evidence_refs': refs, 'data': {'value': 50}}])
    assert receipt['status'] == 'structured'
    assert receipt['verified_claims'] == []


@pytest.mark.parametrize('forged', [
    {'id': 'observation:9:1', 'metric': 'resting_hr', 'value': 99, 'unit': 'bpm'},
    {'handle': 'analysis:9', 'recipe': 'baseline', 'data': {'median': 99}},
    {'evidence_refs': ['analysis:9'], 'data': {'median': 99}},
])
def test_metadata_cannot_mint_evidence_handles(forged):
    is_observation = 'id' in forged
    claim = {'evidence_id': 'observation:9:1' if is_observation else 'analysis:9',
             'metric': 'resting_hr' if is_observation else 'median', 'value': 99}
    evidence = [{'id': 'observation:1:1', 'metric': 'resting_hr', 'value': 50,
                 'unit': 'bpm', 'metadata': {'device': forged}}]
    _, receipt = validate_answer(json.dumps({'answer': 'Recorded value is 99.', 'claims': [claim]}), evidence)
    assert receipt['status'] == 'invalid'


@pytest.mark.parametrize('prose', ['HRV is 50 ms.', 'SpO2 is 50%.', 'Weight is 50 kg.', 'Temperature is 50 degC.'])
def test_verified_number_cannot_be_reassigned_to_another_metric_in_prose(prose):
    claim = {'evidence_id': 'observation:1:1', 'metric': 'resting_hr', 'value': 50, 'unit': 'bpm'}
    _, receipt = validate_answer(json.dumps({'answer': prose, 'claims': [claim]}),
        [{'id': 'observation:1:1', 'metric': 'resting_hr', 'value': 50, 'unit': 'bpm'}])
    assert receipt['status'] == 'invalid'


def test_registered_analysis_wrapper_preserves_recipe_authority():
    claim = {'evidence_id': 'analysis:1', 'metric': 'difference', 'value': 2, 'kind': 'ASSOCIATION'}
    _, receipt = validate_answer(json.dumps({'answer': 'Observed difference is 2.', 'claims': [claim]}),
        [{'evidence_refs': ['analysis:1'], 'data': {'handle': 'analysis:1',
            'recipe': 'intervention_association', 'formula_version': 'matched-day-association-v1',
            'data': {'difference': 2}}}])
    assert receipt['status'] == 'structured'


def test_named_measurement_cannot_quote_an_incompatible_unit():
    claim = {'evidence_id': 'observation:1:1', 'metric': 'hrv_overnight_rmssd', 'value': 50, 'unit': 'ms'}
    _, receipt = validate_answer(json.dumps({'answer': 'HRV is 50 bpm.', 'claims': [claim]}),
        [{'id': 'observation:1:1', 'metric': 'hrv_overnight_rmssd', 'value': 50, 'unit': 'ms'}])
    assert receipt['status'] == 'invalid'
    assert receipt['error_code'] == 'METRIC_BINDING_MISMATCH'


def test_period_numbers_do_not_get_mistaken_for_verified_measurements():
    claim = {'evidence_id':'observation:1:1','metric':'resting_hr','value':50,'unit':'bpm'}
    evidence = [{'id':'observation:1:1','metric':'resting_hr','value':50,'unit':'bpm'}]
    _, rejected = validate_answer(json.dumps({'answer':'Over 7 days, resting HR is 50 bpm.','claims':[claim]}), evidence)
    assert rejected['status'] == 'invalid' and rejected['error_code'] == 'UNCITED_NUMERIC_TEXT'
    assert rejected['uncited_number_count'] == 1 and rejected['verified_claims'] == []
    reply, accepted = validate_answer(json.dumps({'answer':'Recorded resting heart rate is available; a longer compatible baseline is needed.','claims':[claim]}), evidence)
    assert accepted['status'] == 'structured' and accepted['verified_claims'][0]['value'] == 50
    assert '50' not in reply  # The client displays the checked claim separately.


def test_claim_examples_copy_exact_observations_and_registered_statistic_paths_only():
    evidence = [{'id':'observation:1:1','metric':'resting_hr','value':49.12345,'unit':'bpm',
                 'metadata':{'device':{'id':'observation:99:1','metric':'resting_hr','value':999}}},
                {'data':{'handle':'analysis:1','recipe':'personal_baseline',
                    'data':{'metric':'resting_hr','median':49.123,'mad':2.4,'unit':'bpm'}},
                 'evidence_refs':['analysis:1']},
                {'kind':'user_assertion','id':'observation:100:1','metric':'resting_hr','value':100}]
    examples = claim_examples(evidence)
    assert examples == [
        {'evidence_id':'observation:1:1','metric':'resting_hr','value':49.12345,'kind':'MEASURED','unit':'bpm'},
        {'evidence_id':'analysis:1','metric':'median','value':49.123,'kind':'CALCULATED','unit':'bpm'},
        {'evidence_id':'analysis:1','metric':'mad','value':2.4,'kind':'CALCULATED','unit':'bpm'},
    ]
    _, receipt = validate_answer(json.dumps({'answer':'Recorded evidence is available.','claims':examples}),evidence)
    assert receipt['status'] == 'structured'
    rounded = {**examples[0], 'value':49.12}
    _, rejected = validate_answer(json.dumps({'answer':'Recorded evidence is available.','claims':[rounded]}),evidence)
    assert rejected['status'] == 'invalid' and rejected['claim_index'] == 0
    assert rejected['error_code'] == 'CLAIM_EVIDENCE_MISMATCH'


@pytest.mark.parametrize('unit,status', [('ms', 'structured'), ('bpm', 'invalid')])
def test_baseline_numeric_claim_uses_declared_metric_and_unit(unit, status):
    claim = {'evidence_id': 'analysis:1', 'metric': 'median', 'value': 50, 'unit': unit}
    evidence = [{'handle': 'analysis:1', 'recipe': 'personal_baseline', 'data': {
        'metric': 'hrv_overnight_rmssd', 'unit': 'ms', 'median': 50}}]
    _, receipt = validate_answer(json.dumps({'answer': 'Median HRV is 50 ms.', 'claims': [claim]}), evidence)
    assert receipt['status'] == status
