import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from persona_batch import generate_batch

def test_fifty_unique_and_only_selected(tmp_path):
    fields=['risk','patience','detailFind','knowledge.budget']
    with patch('persona_batch.extract_text',return_value={'summary':'test','pools':{k:[0,1,2] for k in fields}}):
        result=generate_batch({'count':50,'fields':fields},tmp_path)
    assert len(result['variants'])==50
    assert len({str(row) for row in result['variants']})==50
    assert all(set(row)==set(fields) for row in result['variants'])

def test_capacity_before_ai(tmp_path):
    with patch('persona_batch.extract_text') as model:
        with pytest.raises(ValueError,match='only 25'):
            generate_batch({'count':50,'fields':['risk','patience']},tmp_path)
        model.assert_not_called()

def test_ai_constraint_capacity(tmp_path):
    with patch('persona_batch.extract_text',return_value={'summary':'restricted','pools':{'risk':[0]}}):
        with pytest.raises(ValueError,match='only 1'):
            generate_batch({'count':3,'fields':['risk']},tmp_path)

def test_role_evidence_and_candidate_oversampling(tmp_path):
    role={'title':'Custom role','background':'Interview-backed baseline'}
    references=[{'name':'P01','text':'Participant: I review defaults.','parameters':{'risk':1}}]
    with patch('persona_batch.extract_text',return_value={'summary':'test','pools':{'risk':[0,1,2]}}) as model:
        result=generate_batch({'count':9,'requestedCount':2,'fields':['risk'],'role':role,'references':references},tmp_path)
    assert len(result['variants'])==3
    prompt=model.call_args.kwargs['_prompt']
    assert 'Custom role' in prompt and 'I review defaults' in prompt
    assert 'Text-only records are not calibrated' in prompt

def test_removed_controls_are_not_generatable(tmp_path):
    for field in ['urgency','stakes','knowledge.navigation','knowledge.operations','knowledge.icons','humanFactors.searchPreference']:
        with patch('persona_batch.extract_text') as model:
            with pytest.raises(ValueError,match='valid parameters'):
                generate_batch({'count':1,'fields':[field]},tmp_path)
            model.assert_not_called()
