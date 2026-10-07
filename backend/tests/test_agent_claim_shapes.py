"""Malformed model claims fail closed instead of crashing the answer boundary."""
import json
import pytest
from app.agent.loop import validate_answer


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
