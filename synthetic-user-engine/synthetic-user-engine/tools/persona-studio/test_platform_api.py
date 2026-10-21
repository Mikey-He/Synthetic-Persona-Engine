"""The platform's workflow rules (platform_api.py): what a workflow's status is, what is refused,
and that credentials go to engine/.env and never into the workflow folder."""
import hashlib
import json

import pytest

import platform_api as api


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(api, 'WORKFLOWS', tmp_path / 'workflows')
    monkeypatch.setattr(api, 'ENGINE', tmp_path / 'engine')
    (tmp_path / 'engine').mkdir()
    (tmp_path / 'engine' / '.env').write_text('GEMINI_API_KEY=keep-me\n', encoding='utf-8')
    return tmp_path


BASICS = {'name': 'Teamspace invite', 'task': 'Invite Priya Shah as a viewer of the Lyra project only.',
          'start': 'http://127.0.0.1:4100/home', 'reset': '/api/reset',
          'login': {'url': '/login', 'user': 'admin@example.test', 'password': 's3cret'}}


def test_a_new_workflow_keeps_its_password_out_of_its_folder(home):
    wid = api.create(dict(BASICS))['id']
    assert wid == 'teamspace-invite'
    folder = home / 'workflows' / wid
    saved = (folder / 'basics.json').read_text(encoding='utf-8')
    assert 's3cret' not in saved and 'admin@example.test' not in saved
    basics = json.loads(saved)
    assert basics['login'] == {'url': '/login', 'user': 'WF_TEAMSPACE_INVITE_USER', 'password': 'WF_TEAMSPACE_INVITE_PASSWORD'}
    env = (home / 'engine' / '.env').read_text(encoding='utf-8')
    assert 'GEMINI_API_KEY=keep-me' in env and 'WF_TEAMSPACE_INVITE_PASSWORD=s3cret' in env
    assert api.create(dict(BASICS))['id'] == 'teamspace-invite-2'


@pytest.mark.parametrize('change, message', [
    ({'start': '/home'}, 'full address'), ({'task': 'Too short'}, 'task'), ({'name': 'x'}, 'name'),
    ({'reset': 'api/reset'}, 'starting with /'), ({'login': {'url': '/login', 'user': 'a'}}, 'both'),
])
def test_bad_basics_are_refused(home, change, message):
    with pytest.raises(ValueError, match=message):
        api.create({**BASICS, **change})


def test_a_workflow_is_ready_only_while_its_checked_flow_is_unchanged(home):
    wid = api.create(dict(BASICS))['id']
    folder = home / 'workflows' / wid
    assert api.status(wid)['key'] == 'new'
    (folder / 'recording').mkdir()
    (folder / 'recording' / 'recording.json').write_text('{}', encoding='utf-8')
    assert api.status(wid)['key'] == 'recorded'
    (folder / 'flow.json').write_text('{"format": "sue-flow"}', encoding='utf-8')
    assert api.status(wid)['key'] == 'draft'
    digest = hashlib.sha1((folder / 'flow.json').read_bytes()).hexdigest()
    (folder / 'check.json').write_text(json.dumps({'passed': True, 'flowHash': digest}), encoding='utf-8')
    assert api.status(wid)['key'] == 'ready'
    (folder / 'flow.json').write_text('{"format": "sue-flow", "name": "edited"}', encoding='utf-8')
    assert api.status(wid)['key'] == 'changed'
    (folder / 'check.json').write_text(json.dumps({'passed': False, 'flowHash': api.flow_hash(folder / 'flow.json')}), encoding='utf-8')
    assert api.status(wid)['key'] == 'failed'


def test_ids_and_screenshot_names_cannot_leave_their_folders(home):
    with pytest.raises(ValueError):
        api.wf_dir('../engine')
    wid = api.create(dict(BASICS))['id']
    assert api.shot_path(wid, '../../engine/.env') is None and api.shot_path(wid, 'state_001.png') is None


def test_a_value_made_unique_reaches_the_task_the_path_and_the_checks(home):
    wid = api.create(dict(BASICS, reset=''))['id']
    folder = home / 'workflows' / wid
    flow = {'format': 'sue-flow', 'name': 'x', 'task': 'Invite priya@x.test as a viewer.',
            'engine': {'plumbing': [{'action': 'type', 'label': 'Email', 'value': 'priya@x.test'}, {'observe': 'priya@x.test'}],
                       'labels': {'consequential': ['Send'], 'advancing': []}, 'words': {'dataTerms': ['priya@x.test']},
                       'target': {'kind': 'web', 'start': 'http://h/', 'success': [
                           {'name': 'invited', 'type': 'json', 'url': '/api/invites', 'where': {'email': 'priya@x.test'},
                            'expect': {'role': 'viewer'}}]}}}
    (folder / 'flow.json').write_text(json.dumps(flow), encoding='utf-8')
    found = api.facts(wid)['facts']
    key = next(f['key'] for f in found if f.get('fixed'))
    assert next(f for f in found if f.get('fixed'))['unique']  # no reset: offered
    api.save_facts({'id': wid, 'facts': [{'key': key, 'on': True, 'unique': True}, {'key': '0:role', 'on': True}]})
    saved = json.loads((folder / 'flow.json').read_text(encoding='utf-8'))
    assert saved['task'] == 'Invite priya+{run}@x.test as a viewer.'
    assert saved['engine']['plumbing'][0]['value'] == 'priya+{run}@x.test'
    assert saved['engine']['target']['success'][0]['where'] == {'email': 'priya+{run}@x.test'}
    assert saved['engine']['target']['success'][0]['expect'] == {'role': 'viewer'}
