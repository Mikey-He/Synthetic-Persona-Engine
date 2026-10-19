"""Survey prose isolation and extraction evidence checks; model calls are not mocked as real runs."""
import json
from pathlib import Path
import sys

import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from survey_text import survey_paragraphs, validate_result


def test_reads_prose_without_turning_structured_choices_into_paragraphs():
    result=survey_paragraphs({'kind':'sue-questionnaire','answers':{
        'background':{'work':'I have an IT role.'},'expNotes':{'X17':'AI helped me once.'},
        'tendStory':'I inspect defaults.','careText':'Worried about unexpected bills.',
        'answers':{'X18':4},'tend':{'R1':2},'vocab':{'river':1}}})
    assert 'I inspect defaults.' in result['text']
    assert 'AI helped me once.' in result['text']
    assert 'another cloud platform' in result['text']
    assert 'X18' not in result['text'] and 'river' not in result['text']


def test_card_does_not_pretend_to_contain_original_background():
    result=survey_paragraphs({'format':'sue-persona','persona':{'name':'Synthetic test fixture'},'goal':{'careText':'Avoid unexpected charges.'}})
    assert '[careText]' in result['text']
    assert '[background.' not in result['text']
    assert 'only careText' in result['source']


def proposal(path='detailCheck', value='2', quote='I check every field.', confidence='explicit'):
    return {'summary':'Checks fields','unknowns':['Vocabulary'], 'updates':[
        {'path':path,'value_json':value,'quote':quote,'confidence':confidence,'reason':'Direct self-report'}]}


def test_validated_proposal_retains_quote_and_native_value():
    result=validate_result(proposal(),'I check every field.')
    assert result['updates'][0]['value']==2
    assert result['updates'][0]['quote']=='I check every field.'


@pytest.mark.parametrize('result',[
    proposal(quote='A made up quote'), proposal(path='searchPreference'), proposal(value='true'),
    proposal(value='11'), proposal(value='2.3'), proposal(path='vocabSize',value='8000',confidence='inferred'),
    proposal(path='confirmBy',value='["list","list"]')
])
def test_rejects_unsupported_or_unverifiable_changes(result):
    with pytest.raises(ValueError):validate_result(result,'I check every field.')


def test_explicit_vocabulary_is_allowed_but_not_invented():
    text='My estimated vocabulary is 8000 words.'
    result=validate_result(proposal('vocabSize','8000',text),text)
    assert result['updates'][0]['value']==8000


def test_generic_interview_json_works_for_any_participant():
    from survey_text import read_interview_document
    for name in ('Participant A','Participant B'):
        result=read_interview_document({'name':name,'transcript':'Interviewer: How do you check? Participant: I inspect defaults.'})
        assert result['name']==name and 'Participant: I inspect defaults.' in result['text']
        assert 'preset' in result['source']


def test_internal_template_is_generic_and_covers_supported_paths():
    from survey_text import TEMPLATE,FIELDS,GROUPS
    assert TEMPLATE['format']=='sue-interview-extraction-template'
    assert len(FIELDS)==len(set(FIELDS))
    assert all('knowledge.'+key in FIELDS for key in GROUPS)
    assert TEMPLATE['evidencePolicy']['unknownIsNotZero']

def test_explicit_configuration_only_human_factors():
    text='I have difficulty reading small text.'
    result=validate_result(proposal('humanFactors.vision','"mild"',text),text)
    assert result['updates'][0]['value']=='mild'
    with pytest.raises(ValueError,match='explicit evidence'):
        validate_result(proposal('humanFactors.vision','"mild"',text,'inferred'),text)
    with pytest.raises(ValueError,match='Invalid human factor'):
        validate_result(proposal('humanFactors.clickPrecision','"perfect"',text),text)

def test_removed_controls_are_not_extractable():
    for field in ['urgency','stakes','knowledge.navigation','knowledge.operations','knowledge.icons','humanFactors.searchPreference']:
        with pytest.raises(ValueError,match='Unsupported extraction field'):
            validate_result(proposal(field,'"calm"'),'I check every field.')
