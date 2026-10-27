"""The platform's own API (engine-design.md 6.3): workflows, personas, runs and results.

A workflow is one task on one product, in one folder: data/version-a for Version A on our UAT
platform, data/workflows/<id> for a workflow onboarded here. Onboarding goes basics -> record
(sue.record, a browser window the researcher does the task in) -> draft (sue.draft) -> review
and confirm in the platform -> checks (sue.check). Only a workflow whose current flow.json
passed its checks is ready for testing; editing it afterwards asks for the checks again.

Everything the engine does runs as a subprocess of the engine's own Python, one at a time.
Credentials a researcher types for a sign-in go to engine/.env only; flow.json names them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / 'data'
ENGINE = ROOT / 'engine'
RUNS = ENGINE / 'runs'
PERSONAS = DATA / 'personas'
RECORDS = DATA / 'studio-configurations'
DELETED = PERSONAS / '.deleted'
WORKFLOWS = DATA / 'workflows'
LEGACY = {'version-a': DATA / 'version-a'}
WF_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,59}$')
CARD = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$')
SHOT = re.compile(r'^state_\d{3}\.png$')
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ROOT / 'tools'))

STATE = {'current': os.environ.get('SUE_WORKFLOW') or 'version-a'}
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def engine_python() -> Path:
    for p in (ENGINE / '.venv' / 'Scripts' / 'python.exe', ENGINE / '.venv' / 'bin' / 'python'):
        if p.exists():
            return p
    return Path(sys.executable)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


# ---- workflows --------------------------------------------------------------------------------

def wf_dir(wid: str) -> Path:
    if not isinstance(wid, str) or not WF_ID.match(wid):
        raise ValueError('That is not a workflow id.')
    folder = LEGACY.get(wid) or WORKFLOWS / wid
    if not folder.is_dir():
        raise ValueError('No such workflow.')
    return folder


def ids() -> list[str]:
    out = [w for w, d in LEGACY.items() if (d / 'flow.json').exists()]
    if WORKFLOWS.is_dir():
        out += sorted(d.name for d in WORKFLOWS.iterdir() if d.is_dir() and WF_ID.match(d.name))
    return out


def flow_hash(path: Path) -> str | None:
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.exists() else None


def job_for(wid: str, kinds=('record', 'draft', 'check')) -> dict | None:
    with LOCK:
        return next((j for j in JOBS.values() if j.get('workflow') == wid and j['kind'] in kinds and j['proc'].poll() is None), None)


def status(wid: str) -> dict:
    folder = wf_dir(wid)
    flow, check = folder / 'flow.json', read_json(folder / 'check.json')
    running = job_for(wid)
    if running:
        return {'key': running['kind'] + 'ing', 'label': {'record': 'Recording', 'draft': 'Drafting', 'check': 'Checking'}[running['kind']]}
    if wid in LEGACY:
        return {'key': 'ready', 'label': 'Ready'}  # Version A: checked against people over many rounds
    if not flow.exists():
        rec = folder / 'recording' / 'recording.json'
        return {'key': 'recorded', 'label': 'Recorded'} if rec.exists() else {'key': 'new', 'label': 'Not recorded yet'}
    if not check:
        return {'key': 'draft', 'label': 'Needs review'}
    if check.get('flowHash') != flow_hash(flow):
        return {'key': 'changed', 'label': 'Changed since checked'}
    return {'key': 'ready', 'label': 'Ready'} if check.get('passed') else {'key': 'failed', 'label': 'Checks failed'}


def summary(wid: str) -> dict:
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json', {}) or {}
    basics = read_json(folder / 'basics.json', {}) or {}
    target = ((flow.get('engine') or {}).get('target') or {'kind': 'uat'})
    return {'id': wid, 'name': flow.get('name') or basics.get('name') or wid, 'product': basics.get('product', ''),
            'start': target.get('start') or basics.get('start') or '', 'kind': target.get('kind', 'uat'),
            'task': flow.get('task') or basics.get('task', ''), 'steps': len(flow.get('steps') or []),
            'items': len(flow.get('items') or []), 'status': status(wid), 'current': STATE['current'] == wid,
            'outcome': ((flow.get('engine') or {}).get('outcome') or {}).get('kind', 'change'),
            'legacy': wid in LEGACY}


def list_workflows() -> dict:
    return {'current': STATE['current'], 'workflows': [summary(w) for w in ids()]}


def current_flow_path() -> Path:
    return wf_dir(STATE['current']) / 'flow.json'


def select(body) -> dict:
    wid = body.get('id')
    folder = wf_dir(wid)
    if not (folder / 'flow.json').exists():
        raise ValueError('This workflow has no flow yet. Record and review it first.')
    STATE['current'] = wid
    os.environ['SUE_FLOW'] = str(folder / 'flow.json')
    import workflow as studio_flow  # Persona Studio's reader caches per path
    studio_flow._cache.clear()
    return list_workflows()


def slug(name: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:48] or 'workflow'
    out, n = s, 2
    while (WORKFLOWS / out).exists() or out in LEGACY:
        out, n = f'{s}-{n}', n + 1
    return out


def env_name(wid: str, what: str) -> str:
    return 'WF_' + re.sub(r'[^A-Z0-9]+', '_', wid.upper()) + '_' + what


def put_env(values: dict[str, str]) -> None:
    """Writes credentials into engine/.env (never into the workflow folder)."""
    path = ENGINE / '.env'
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    keep = [ln for ln in lines if ln.split('=', 1)[0].strip() not in values]
    keep += [f'{k}={v}' for k, v in values.items()]
    path.write_text('\n'.join(keep) + '\n', encoding='utf-8')
    for k, v in values.items():
        os.environ[k] = v


def clean_url(value: str, field: str, relative=False) -> str:
    value = (value or '').strip()
    if relative:
        if value and not value.startswith('/'):
            raise ValueError(f'{field} is a path on the product, starting with /.')
        return value
    p = urlparse(value)
    if p.scheme not in ('http', 'https') or not p.netloc:
        raise ValueError(f'{field} must be a full address, starting with http:// or https://.')
    return value


def basics_from(body: dict, wid: str | None = None) -> tuple[dict, dict]:
    name, task = (body.get('name') or '').strip(), (body.get('task') or '').strip()
    if not 3 <= len(name) <= 80:
        raise ValueError('Give the workflow a name of 3 to 80 characters.')
    if not 20 <= len(task) <= 4000:
        raise ValueError('Write the task as participants will read it (20 to 4,000 characters).')
    basics = {'name': name, 'task': task, 'product': (body.get('product') or '').strip()[:200],
              'users': (body.get('users') or '').strip()[:400], 'start': clean_url(body.get('start'), 'The start page')}
    reset = clean_url(body.get('reset'), 'The reset address', relative=True)
    if reset:
        basics['reset'] = reset
    secrets_out = {}
    login = body.get('login') or {}
    if login.get('mode') == 'session':  # single sign-on: signed in by hand once, while recording
        basics['login'] = {'mode': 'session', 'file': 'session.json'}
    elif login.get('url'):
        basics['login'] = {'url': clean_url(login['url'], 'The sign-in page', relative=True)}
        if login.get('user') or login.get('password'):
            if not login.get('user') or not login.get('password'):
                raise ValueError('Give both the test account and its password, or neither.')
            secrets_out = {'user': login['user'], 'password': login['password']}
    return basics, secrets_out


def create(body) -> dict:
    basics, creds = basics_from(body)
    wid = slug(basics['name'])
    folder = WORKFLOWS / wid
    folder.mkdir(parents=True)
    if 'login' in basics and not by_hand(basics):
        basics['login'].update(user=env_name(wid, 'USER'), password=env_name(wid, 'PASSWORD'))
        if creds:
            put_env({basics['login']['user']: creds['user'], basics['login']['password']: creds['password']})
    write_json(folder / 'basics.json', basics)
    return {'id': wid}


def by_hand(basics: dict) -> bool:
    return (basics.get('login') or {}).get('mode') == 'session'


def update_basics(wid: str, body) -> dict:
    folder = wf_dir(wid)
    if wid in LEGACY:
        raise ValueError('Version A is defined in its own flow.json.')
    old = read_json(folder / 'basics.json', {}) or {}
    basics, creds = basics_from(body)
    if 'login' in basics and not by_hand(basics):
        basics['login'].update(user=env_name(wid, 'USER'), password=env_name(wid, 'PASSWORD'))
        if creds:
            put_env({basics['login']['user']: creds['user'], basics['login']['password']: creds['password']})
    write_json(folder / 'basics.json', basics)
    flow = read_json(folder / 'flow.json')
    if flow:  # the task and the product's addresses live in the flow too
        flow['name'], flow['task'] = basics['name'], basics['task']
        target = flow.setdefault('engine', {}).setdefault('target', {'kind': 'web', 'success': []})
        target['start'] = basics['start']
        for key in ('login', 'reset'):
            target.pop(key, None)
        if 'login' in basics:
            target['login'] = basics['login']
        if basics.get('reset'):
            target['reset'] = {'method': 'POST', 'url': basics['reset']}
        write_json(folder / 'flow.json', flow)
    return detail(wid) | {'renamed': old.get('name') != basics['name']}


def flow_problems(flow: dict) -> list[str]:
    from sue.workflow import problems as engine_problems
    from sync_flow import problems as all_problems  # questionnaire, Persona Studio and the engine
    try:
        return all_problems(flow)
    except (KeyError, TypeError, AttributeError) as error:
        return [f'The flow is incomplete: {error}'] + engine_problems(flow)


def recording_view(folder: Path) -> dict | None:
    rec = read_json(folder / 'recording' / 'recording.json')
    if not rec:
        return None
    return {'start': rec.get('start'), 'viewport': rec.get('viewport'), 'endedAt': rec.get('endedAt'),
            'states': [{'n': s['n'], 'route': s['route'], 'title': s.get('title', ''), 'shot': s['shot'],
                        'size': s.get('scroll'), 'controls': s['controls']} for s in rec.get('states', [])],
            'actions': [{k: a.get(k) for k in ('n', 'before', 'after', 'action', 'value', 'secret', 'control')}
                        for a in rec.get('actions', [])],
            'saved': [r for r in rec.get('network') or [] if r['method'] != 'GET' and r.get('sent')],
            'capabilities': rec.get('capabilities') or {},
            'setup': bool(read_json(folder / 'recording' / 'setup.json')), 'cleanup': bool(read_json(folder / 'recording' / 'cleanup.json'))}


def detail(wid: str) -> dict:
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    notes = (read_json(folder / 'draft-notes.json', {}) or {}).get('notes', [])
    out = summary(wid) | {'basics': read_json(folder / 'basics.json', {}) or {}, 'flow': flow, 'notes': notes,
                          'recording': recording_view(folder), 'check': read_json(folder / 'check.json'),
                          'problems': flow_problems(flow) if flow else []}
    job = job_for(wid)
    out['job'] = job['id'] if job else None
    return out


def save_flow(wid: str, body) -> dict:
    folder = wf_dir(wid)
    flow = body.get('flow')
    if not isinstance(flow, dict) or flow.get('format') != 'sue-flow':
        raise ValueError('Send the whole flow (format sue-flow).')
    if job_for(wid):
        raise ValueError('Wait for the recording, draft or check to finish first.')
    problems = flow_problems(flow)
    write_json(folder / 'flow.json', flow)
    return {'problems': problems, 'status': status(wid)}


def pick_control(wid: str, body) -> dict:
    """The locator for a control the reviewer pointed at on a recorded screen."""
    from sue import locate
    rec = read_json(wf_dir(wid) / 'recording' / 'recording.json') or {}
    n, i = body.get('state'), body.get('control')
    states = rec.get('states') or []
    if type(n) is not int or not 0 <= n < len(states) or type(i) is not int or not 0 <= i < len(states[n]['controls']):
        raise ValueError('Point at a control on a recorded screen.')
    controls = states[n]['controls']
    loc = locate.build(controls, i)
    return {'locate': loc, 'route': states[n]['route'], 'found': locate.find(controls, loc)}


def shot_path(wid: str, name: str) -> Path | None:
    if not SHOT.match(name or ''):
        return None
    path = wf_dir(wid) / 'recording' / name
    return path if path.is_file() else None


# ---- jobs: record, draft, check, run --------------------------------------------------------------

def busy() -> dict | None:
    with LOCK:
        return next((j for j in JOBS.values() if j['proc'].poll() is None), None)


def start(kind: str, cmd: list[str], **meta) -> dict:
    other = busy()
    if other:
        raise ValueError(f'The engine is busy ({other["kind"]} {other.get("label", "")}). Wait for it or stop it first.')
    RUNS.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex[:12]
    log_path = RUNS / f'platform-{kind}-{jid}.log'
    log = log_path.open('w', encoding='utf-8')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', SUE_FLOW=meta.pop('flow', os.environ.get('SUE_FLOW', '')))
    if not env['SUE_FLOW']:
        env.pop('SUE_FLOW')
    proc = subprocess.Popen(cmd, cwd=ENGINE, stdout=log, stderr=subprocess.STDOUT, env=env,
                            creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    with LOCK:
        JOBS[jid] = {'id': jid, 'kind': kind, 'proc': proc, 'log': log_path, 'logfile': log, 'started': time.time(),
                     'stopped': False, **meta}
    return {'id': jid}


def job_state(job: dict) -> str:
    code = job['proc'].poll()
    if code is not None and not job['logfile'].closed:
        job['logfile'].close()
    return 'running' if code is None else 'stopped' if job['stopped'] else 'completed' if code == 0 else 'failed'


def get_job(jid: str) -> dict:
    with LOCK:
        job = JOBS.get(jid)
    if not job:
        raise ValueError('No such job.')
    return job


def log_text(job: dict) -> str:
    return job['log'].read_text(encoding='utf-8', errors='replace') if job['log'].exists() else ''


def stop_job(body) -> dict:
    job = get_job(body.get('id'))
    if job['proc'].poll() is None:
        job['stopped'] = True
        if job['kind'] == 'record':
            (wf_dir(job['workflow']) / 'recording' / 'STOP').write_text('stop', encoding='utf-8')
        else:
            job['proc'].terminate()
    return {'stopped': True}


def record(wid: str, body) -> dict:
    """name: the task (recording), or what the engine does itself before (setup) or after (cleanup)
    each run, for a product with no reset address."""
    folder = wf_dir(wid)
    if wid in LEGACY:
        raise ValueError('Version A runs on our own platform and is not recorded here.')
    basics = read_json(folder / 'basics.json') or {}
    name = body.get('name') or 'recording'
    if name not in ('recording', 'setup', 'cleanup'):
        raise ValueError('Record the task, its set-up or its clean-up.')
    py = str(engine_python())
    cmd = [py, '-m', 'sue.record', '--start', basics['start'], '--out', str(folder / 'recording'), '--name', name]
    login = basics.get('login')
    if by_hand(basics):
        cmd += ['--session', str(folder / 'session.json')]
        if name == 'recording' or not (folder / 'session.json').exists():
            cmd.append('--sign-in-by-hand')
    elif login:
        cmd += ['--login-url', login['url'], '--user', login['user'], '--password', login['password']]
    if basics.get('reset'):
        cmd += ['--reset', basics['reset']]
    if isinstance(body.get('auto'), str) and Path(body['auto']).is_file():  # tests drive the browser themselves
        cmd += ['--auto', body['auto'], '--headless']
    elif name == 'recording' and body.get('written') is not None:  # the researcher wrote the steps; AI does them once
        lines = [ln.strip(' -\t') for ln in str(body['written']).splitlines() if ln.strip(' -\t')]
        if not 1 <= len(lines) <= 40 or any(len(ln) > 300 for ln in lines):
            raise ValueError('Write the steps one per line: 1 to 40 lines, each under 300 characters.')
        (folder / 'written.txt').write_text('\n'.join(lines), encoding='utf-8')
        cmd += ['--written', str(folder / 'written.txt'), '--task', basics['task']]
        if body.get('headless'):
            cmd.append('--headless')
    return start('record', cmd, workflow=wid, label=basics.get('name', wid), name=name)


def import_flow(body) -> dict:
    """A workflow file made elsewhere (the format Version A uses), for a website: checked here,
    then on the product itself by the readiness checks, like a recorded one."""
    flow = body.get('flow')
    if not isinstance(flow, dict) or flow.get('format') != 'sue-flow':
        raise ValueError('This is not a workflow file (format sue-flow).')
    target = (flow.get('engine') or {}).get('target') or {}
    if target.get('kind') != 'web':
        raise ValueError('Only workflow files for a website can be imported: engine.target.kind must be "web".')
    start = clean_url(target.get('start'), 'The start page in the file')
    problems = flow_problems(flow)
    if problems:
        raise ValueError('The file has problems: ' + '; '.join(problems[:5]))
    basics = {'name': (flow.get('name') or '').strip()[:80] or 'Imported test', 'task': flow.get('task') or '', 'product': '',
              'users': '', 'start': start, 'imported': True}
    if (target.get('reset') or {}).get('url'):
        basics['reset'] = target['reset']['url']
    wid = slug(basics['name'])
    folder = WORKFLOWS / wid
    folder.mkdir(parents=True)
    login = target.get('login') or {}
    if login.get('mode') == 'session':
        basics['login'] = {'mode': 'session', 'file': 'session.json'}
    elif login.get('url'):
        user, password = env_name(wid, 'USER'), env_name(wid, 'PASSWORD')
        basics['login'] = {'url': login['url'], 'user': user, 'password': password}
        if body.get('user') or body.get('password'):
            put_env({user: body.get('user') or '', password: body.get('password') or ''})
        target['login'] = {**login, 'user': user, 'password': password}
    write_json(folder / 'basics.json', basics)
    write_json(folder / 'flow.json', flow)
    return {'id': wid, 'needsAccount': bool(login.get('url')) and not (body.get('user') and body.get('password'))}


def signed_in(body) -> dict:
    """The researcher has signed in by hand in the recording window."""
    folder = wf_dir(body.get('id'))
    (folder / 'recording' / 'SIGNED_IN').write_text('yes', encoding='utf-8')
    return {'ok': True}


def use_steps(body) -> dict:
    """A set-up or clean-up just recorded goes into the flow as steps the engine replays."""
    from sue.draft import replay_steps
    wid, name = body.get('id'), body.get('name')
    folder = wf_dir(wid)
    if name not in ('setup', 'cleanup'):
        raise ValueError('Set-up or clean-up.')
    rec = read_json(folder / 'recording' / f'{name}.json')
    flow = read_json(folder / 'flow.json')
    if not rec or not flow:
        raise ValueError('Record it first.')
    steps = replay_steps(rec)
    flow['engine']['target'][name] = steps
    write_json(folder / 'flow.json', flow)
    return {'steps': steps, 'status': status(wid)}


def record_view(job: dict) -> dict:
    folder = wf_dir(job['workflow'])
    rec = read_json(folder / 'recording' / f"{job.get('name') or 'recording'}.json") or {}
    acts = [a for a in rec.get('actions') or [] if a['action'] not in ('newtab', 'download')]
    return {'actions': [{'n': a['n'], 'action': a['action'], 'value': '' if a.get('secret') else a.get('value'),
                         'name': (a.get('control') or {}).get('text') or (a.get('control') or {}).get('label') or '',
                         'route': rec['states'][a['after']]['route']} for a in acts],
            'screens': len(rec.get('states') or []), 'name': job.get('name') or 'recording', 'stuck': rec.get('stuck'),
            'waitingForSignIn': not rec and by_hand(read_json(folder / 'basics.json') or {}) and job.get('name') == 'recording'}


def draft(wid: str, body) -> dict:
    folder = wf_dir(wid)
    if not (folder / 'recording' / 'recording.json').exists():
        raise ValueError('Record the task first.')
    if (folder / 'flow.json').exists():
        shutil.copy2(folder / 'flow.json', folder / 'flow.prev.json')
    return start('draft', [str(engine_python()), '-m', 'sue.draft', '--recording', str(folder / 'recording' / 'recording.json'),
                           '--basics', str(folder / 'basics.json'), '--out', str(folder / 'flow.json')],
                 workflow=wid, label=wid)


def check(wid: str, body) -> dict:
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    if not flow:
        raise ValueError('There is no flow to check yet.')
    problems = flow_problems(flow)
    if problems:
        raise ValueError('Fix these first: ' + '; '.join(problems[:5]))
    cmd = [str(engine_python()), '-m', 'sue.check', '--flow', str(folder / 'flow.json')]
    if body.get('withModel'):
        cmd.append('--with-model')
    return start('check', cmd, workflow=wid, label=wid, flow=str(folder / 'flow.json'))


def check_view(job: dict) -> dict:
    text = log_text(job)
    return {'lines': [ln.strip() for ln in text.splitlines() if re.match(r'^(=== |\s+\[(pass|FAIL|warn)\])', ln)][-10:],
            'started': [m for m in re.findall(r'^=== (\w+) \(', text, flags=re.M)]}


# ---- personas -------------------------------------------------------------------------------------

def current_name() -> str:
    return (read_json(current_flow_path(), {}) or {}).get('name', '')


def scores_of(card: dict) -> dict:
    """0-10 scores for the chips and sliders: a v3 card's own, a v2 card's levels as 0, 5, 10."""
    t = card.get('tendency') or {}
    level = {'low': 0, 'medium': 5, 'high': 10}
    out = {k: (t.get(k) or {}).get('score', level.get((t.get(k) or {}).get('level'), 5)) for k in ('risk', 'patience', 'detailFind', 'detailCheck')}
    st = card.get('state') or {}
    out.update({k: (st.get(k) or {}).get('score', 0) if isinstance(st.get(k), dict) else (st.get(k) or 0)
                for k in ('fatigue', 'distraction', 'timePressure')})
    return out


def known_share(card: dict) -> float:
    items = [i for i in card.get('items') or [] if i.get('kind') != 'habit']
    return round(sum(i.get('result') == 'understands' for i in items) / len(items), 2) if items else 0


def persona_entry(path: Path, card: dict) -> dict:
    cid = path.stem
    record = read_json(RECORDS / path.name) if cid.startswith('studio-') else None
    kind = 'studio' if record else 'self' if (card.get('persona') or {}).get('cardType') in ('full', 'blank') else 'participant'
    return {'id': cid, 'name': (card.get('persona') or {}).get('name') or cid, 'kind': kind, 'version': card.get('version'),
            'description': (record or {}).get('description') or '', 'parameters': (record or {}).get('parameters'),
            'from': (record or {}).get('source'),
            'scores': scores_of(card), 'known': known_share(card), 'builtAt': card.get('builtAt')}


def list_personas() -> dict:
    """Only the personas made on the platform, from what the researcher gave it. The research cards
    in data/personas (participants, sweeps, the self-test cards) stay for the engine's own
    calibration and are not shown."""
    name = current_name()
    out = []
    for path in sorted(PERSONAS.glob('studio-*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        card = read_json(path)
        if isinstance(card, dict) and card.get('format') == 'sue-persona' and card.get('flow') == name and (RECORDS / path.name).exists():
            out.append(persona_entry(path, card))
    return {'workflow': name, 'personas': out, 'selfTest': []}


def draft_persona(body) -> dict:
    from ai_api import complete_json, settings as ai_settings
    prompt = body.get('prompt')
    if not isinstance(prompt, str) or not 20 <= len(prompt) <= 20000:
        raise ValueError('Describe the persona first.')
    cfg = ai_settings()
    cfg = {**cfg, 'json_mode': 'json_object'}  # the settings are checked by PersonaParameters.fromJSON
    result = complete_json(prompt, {'type': 'object'}, cfg)
    return {'settings': result}


def save_persona(body, save_card) -> dict:
    description = (body.get('description') or '').strip()[:2000]
    card = body.get('card') or {}
    if card.get('flow') != current_name():
        raise ValueError('This card was built for another workflow; reload the page.')
    result = save_card(body)
    record = RECORDS / (result['id'] + '.json')
    data = read_json(record, {}) or {}
    data['description'] = description
    if body.get('source') == 'survey':  # built from a real participant's survey answers
        data['source'] = 'survey'
    write_json(record, data)
    return result


def update_persona(body) -> dict:
    cid = body.get('id')
    if not isinstance(cid, str) or not re.match(r'^studio-[0-9a-f]{32}$', cid) or not (PERSONAS / f'{cid}.json').exists():
        raise ValueError('Only personas made here can be edited; duplicate a card to change it.')
    card, parameters = body.get('card'), body.get('parameters')
    if not isinstance(card, dict) or card.get('format') != 'sue-persona' or card.get('version') != 3 or not isinstance(parameters, dict):
        raise ValueError('Send the rebuilt v3 card and its settings.')
    if card.get('flow') != current_name():
        raise ValueError('This card was built for another workflow; reload the page.')
    data = read_json(RECORDS / f'{cid}.json', {}) or {}
    if data.get('source') == 'questionnaire':  # keep what their answers decided, except what was changed
        card = keep_answers(card, data['baseCard'], data['baseParameters'], parameters)
    write_json(PERSONAS / f'{cid}.json', card)
    data.update(parameters=parameters, nativeAnswers=body.get('answers') or data.get('nativeAnswers'),
                description=(body.get('description') or data.get('description') or '').strip()[:2000])
    write_json(RECORDS / f'{cid}.json', data)
    return {'id': cid}


def delete_persona(body, restore=False) -> dict:
    cid = body.get('id')
    if not isinstance(cid, str) or not CARD.match(cid) or cid in ('full', 'blank', 'full-card', 'blank-card'):
        raise ValueError('That card cannot be deleted here.')
    DELETED.mkdir(parents=True, exist_ok=True)
    pairs = [(PERSONAS / f'{cid}.json', DELETED / f'{cid}.json'), (RECORDS / f'{cid}.json', DELETED / f'{cid}.record.json')]
    moved = 0
    for live, gone in pairs:
        src, dst = (gone, live) if restore else (live, gone)
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved += 1
    if not moved:
        raise ValueError('No such card.')
    return {'id': cid, 'restored' if restore else 'deleted': True}


# ---- runs and results -------------------------------------------------------------------------------

def reachable(flow: dict) -> tuple[bool, str]:
    target = (flow.get('engine') or {}).get('target') or {'kind': 'uat'}
    if target.get('kind') == 'web':
        url = target['start']
    else:
        from sue.config import load_config
        url = load_config(flow=current_flow_path())['platform']['base_url']
    try:
        with urlopen(url, timeout=3) as r:
            return r.status < 500, url
    except Exception as error:  # noqa: BLE001 - redirects to sign-in still count as up
        code = getattr(error, 'code', None)
        return bool(code and code < 500), url


def start_tests(body) -> dict:
    wid = STATE['current']
    if status(wid)['key'] != 'ready':
        raise ValueError('This workflow is not ready: run its checks first.')
    cards, runs = body.get('cards'), body.get('runs', 5)
    if not isinstance(cards, list) or not 1 <= len(cards) <= 20 or type(runs) is not int or not 1 <= runs <= 10:
        raise ValueError('Choose 1 to 20 personas and 1 to 10 runs each.')
    name = current_name()
    for c in cards:
        if c in ('full', 'blank'):
            continue
        card = read_json(PERSONAS / f'{c}.json') if isinstance(c, str) and CARD.match(c) else None
        if not card or card.get('flow') != name:
            raise ValueError(f'{c} is not a persona of this workflow.')
    flow = read_json(current_flow_path())
    up, url = reachable(flow)
    if not up:
        raise ValueError(f'The product is not reachable at {url}. Start it and try again.')
    cmd = [str(engine_python()), '-m', 'sue.batch', '--flow', str(current_flow_path()), '--runs', str(runs), '--live']
    for c in cards:
        cmd += ['--card', c]
    return start('run', cmd, workflow=wid, label=f'{len(cards)} personas', cards=cards, runs=runs, flow=str(current_flow_path()))


def run_view(job: dict) -> dict:
    text = log_text(job)
    done, current = [], None
    for block in re.split(r'^##### ', text, flags=re.M)[1:]:
        head = re.match(r'(.+?), run (\d+) of (\d+)', block)
        if not head:
            continue
        card, n = head.group(1), int(head.group(2))
        grade = re.search(r'^Grading: (pass|fail)', block, flags=re.M)
        finished = re.search(r'^=== Finished: (\w+) \((.*)\);', block, flags=re.M)
        steps = re.findall(r'^\s+(\d+) (\S+)\s+(.*)$', block, flags=re.M)
        if grade:
            done.append({'card': card, 'run': n, 'pass': grade.group(1) == 'pass',
                         'stop': finished.group(1) if finished else '', 'why': finished.group(2) if finished else ''})
        else:
            last = steps[-1] if steps else None
            current = {'card': card, 'run': n, 'step': int(last[0]) if last else 0, 'route': last[1] if last else '',
                       'did': last[2][:140] if last else 'Opening the product'}
    batch = re.findall(r'^Saved to (.+batch-[0-9-]+)\s*$', text, flags=re.M)
    error = None
    if job_state(job) == 'failed':
        tail = [ln for ln in text.strip().splitlines() if ln.strip()][-3:]
        error = ' '.join(tail)[-400:]
    return {'done': done, 'current': current, 'cards': job.get('cards'), 'runs': job.get('runs'),
            'batch': Path(batch[-1].strip()).name if batch else None, 'error': error}


def live_view(job: dict) -> dict:
    """What the run going on now shows: its screen as it is, where the pointer is and what was
    clicked (live.json, written by the engine's LiveFeed), and its last steps."""
    dirs = [d for d in RUNS.iterdir() if d.is_dir() and re.match(r'^\d{8}-\d{6}-', d.name) and d.stat().st_mtime >= job['started'] - 2]
    if not dirs:
        return {'frame': None, 'state': None, 'steps': []}
    d = max(dirs, key=lambda p: p.stat().st_mtime)
    steps = []
    path = d / 'steps.jsonl'
    if path.exists():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines()[-8:]:
            try:
                s = json.loads(line)
            except ValueError:
                continue
            a = s.get('action') or {}
            steps.append({'step': s['step'], 'route': s.get('route'), 'rule': s.get('rule'), 'looking': s.get('looking_at'),
                          'did': f"{a.get('type', '')} {a.get('original') or a.get('text') or ''}".strip(),
                          'why': next((c.get('why') for c in s.get('candidates') or [] if c.get('element') == a.get('element')), '')})
    run = read_json(d / 'run.json', {}) or {}
    state = read_json(d / 'live.json')
    frame = f'/runs/{d.name}/live.jpg' if (d / 'live.jpg').exists() else None
    if not frame:  # a run without the live feed: its newest screenshot
        shots = sorted(d.glob('step_*.png'))
        frame = f'/runs/{d.name}/{shots[-1].name}' if shots else None
    return {'dir': d.name, 'card': run.get('persona'), 'seed': run.get('seed'), 'frame': frame, 'state': state, 'steps': steps}


def batch_workflow(data: dict) -> str:
    return data.get('workflow') or 'Version A · Cloud Console (prototype) budget setup'


def list_results() -> dict:
    name = current_name()
    out = []
    if RUNS.is_dir():
        for d in sorted((p for p in RUNS.iterdir() if p.is_dir() and p.name.startswith('batch-')), reverse=True):
            data = read_json(d / 'batch.json')
            if not data or batch_workflow(data) != name:
                continue
            if not all(str(c.get('card', '')).startswith('studio-') and (PERSONAS / f"{c['card']}.json").exists() for c in data.get('cards') or []):
                continue  # the engine's own research runs, not tests of the platform's personas
            cards = data.get('cards') or []
            runs = sum(c.get('runs', 0) for c in cards)
            out.append({'id': d.name, 'at': data.get('at') or d.name[6:], 'runs': runs, 'passed': sum(c.get('passed', 0) for c in cards),
                        'cards': [c['card'] for c in cards]})
    return {'workflow': name, 'results': out[:50]}


def run_summary(run_dir: str) -> dict:
    d = RUNS / Path(run_dir).name
    s = read_json(d / 'summary.json', {}) or {}
    last = None
    path = d / 'steps.jsonl'
    if path.exists():
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        if lines:
            try:
                last = json.loads(lines[-1])
            except ValueError:
                last = None
    return {'dir': d.name, 'card': s.get('card'), 'seed': s.get('seed'), 'evaluation': s.get('evaluation'),
            'stop': s.get('stop'), 'actions': s.get('actions'), 'wrong': s.get('wrong'), 'backs': s.get('backs'),
            'missed': s.get('missed_defaults') or [], 'slips': s.get('slips') or {}, 'seconds': s.get('seconds'),
            'lastRoute': (last or {}).get('route'), 'lastRule': (last or {}).get('rule'),
            'report': f'/runs/{d.name}/report.html' if (d / 'report.html').exists() else None}


def result_detail(bid: str) -> dict:
    if not re.match(r'^batch-[0-9-]+$', bid or ''):
        raise ValueError('That is not a result.')
    data = read_json(RUNS / bid / 'batch.json')
    if not data:
        raise ValueError('No such result.')
    names = {p.stem: (read_json(p, {}) or {}).get('persona', {}).get('name') for c in data['cards'] for p in [PERSONAS / f"{c['card']}.json"]}
    names.update({'full': 'Full card', 'blank': 'Blank card'})
    from journey import baseline, journey
    flow = read_json(current_flow_path()) or {}
    base = baseline(flow, RUNS) if flow else None

    def with_path(r: str) -> dict:
        d = RUNS / Path(r).name
        out = run_summary(r)
        try:
            out['path'] = journey(flow, d, f'/runs/{d.name}', base)['steps'] if flow.get('name') == batch_workflow(data) else None
        except (OSError, ValueError, KeyError, IndexError):
            out['path'] = None
        return out

    return {'id': bid, 'workflow': batch_workflow(data), 'at': data.get('at') or bid[6:], 'person': data.get('person'),
            'steps': [{'id': s['id'], 'action': s['action'], 'hard': s.get('defaults') or ''} for s in flow.get('steps') or []],
            'cards': [{**{k: c.get(k) for k in ('card', 'runs', 'passed', 'checks_passed', 'missed_defaults', 'slips', 'stops', 'actions')},
                       'name': names.get(c['card']) or c['card'], 'runList': [with_path(r) for r in c.get('run_dirs', [])]}
                      for c in data['cards']]}


# ---- the persona builder, holding the current workflow ---------------------------------------------

def builder_page() -> bytes:
    """tools/persona-builder.html with the current flow in its flow block, so a card is built for
    the workflow being tested without rewriting the file (tools/sync_flow.py still does that)."""
    from sync_flow import dump
    text = (ROOT / 'tools' / 'persona-builder.html').read_text(encoding='utf-8')
    flow = read_json(current_flow_path())
    block = re.compile(r'(<script type="application/json" id="flow">)(.*?)(</script>)', re.S)
    m = block.search(text)
    if not m or not flow:
        return text.encode('utf-8')
    return (text[:m.start(2)] + dump(flow) + text[m.end(2):]).encode('utf-8')


def questionnaire_page() -> bytes:
    """tools/questionnaire.html with the current workflow's task and experience questions, for
    real participants of a workflow onboarded here."""
    from sync_flow import dump, questionnaire_data
    text = (ROOT / 'tools' / 'questionnaire.html').read_text(encoding='utf-8')
    flow = read_json(current_flow_path())
    block = re.compile(r'(<script type="application/json" id="qdata">)(.*?)(</script>)', re.S)
    m = block.search(text)
    if not m or not flow:
        return text.encode('utf-8')
    return (text[:m.start(2)] + dump(questionnaire_data(flow)) + text[m.end(2):]).encode('utf-8')


# ---- what must be right at the end, in plain words ------------------------------------------------

def _words(field: str) -> str:
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', str(field)).replace('_', ' ').strip().lower()


def _show(value) -> str:
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, list):
        return ', '.join(map(str, value)) + (' only' if len(value) == 1 else '') if value else 'none'
    return str(value)


def _mentions(task: str, value) -> bool:
    vals = value if isinstance(value, list) else [value]
    return any(isinstance(v, str) and len(v) > 1 and v.lower() in task.lower() for v in vals)


def facts(wid: str) -> dict:
    """The success checks of a drafted flow as sentences to tick: for a check of what was saved, one
    sentence per value the product saved, ticked when the check expects it; for the others, the
    check itself."""
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    if not flow:
        raise ValueError('There is no draft yet.')
    rec = read_json(folder / 'recording' / 'recording.json') or {}
    sent = [r for r in rec.get('network') or [] if r['method'] != 'GET' and isinstance(r.get('sent'), dict)]
    task, out = flow.get('task', ''), []
    basics = read_json(folder / 'basics.json') or {}
    target = (flow.get('engine') or {}).get('target') or {}
    no_reset = not target.get('reset') and not target.get('cleanup') and any(c.get('type') in ('json', 'text') for c in target.get('success') or [])
    for i, c in enumerate(target.get('success') or []):
        t = c.get('type')
        if t in ('json', 'storage'):
            where, expect = c.get('where') or {}, c.get('expect') or {}
            body = stored_row(rec, c) if t == 'storage' else \
                next((r['sent'] for r in sent if r['path'] == c.get('url')), None) or (sent[-1]['sent'] if sent else {})
            for k, v in where.items():
                out.append({'key': f'{i}:where:{k}', 'check': i, 'field': k, 'value': v, 'fixed': True, 'on': True,
                            'text': f'{_words(k).capitalize()}: {_show(v)}', 'why': 'How the new one is found',
                            'unique': no_reset and isinstance(v, str) and '{run}' not in v, 'isUnique': isinstance(v, str) and '{run}' in v})
            for k in list(expect) + [k for k in body if k not in expect and k not in where]:
                v = body[k] if k in body else expect.get(k)  # as the product saved it, not as the draft wrote it
                out.append({'key': f'{i}:{k}', 'check': i, 'field': k, 'value': v, 'on': k in expect,
                            'text': f'{_words(k).capitalize()}: {_show(v)}',
                            'why': 'The task mentions it' if _mentions(task, v) else ('In the draft' if k in expect else 'The task does not mention it')})
        elif t == 'answer':
            out.append({'key': f'{i}', 'check': i, 'on': True, 'answer': c.get('expected') or [],
                        'text': 'They report the answer: ' + ' or '.join(map(str, c.get('expected') or [])), 'why': 'What the task asks'})
        elif t == 'text':
            out.append({'key': f'{i}', 'check': i, 'on': True, 'text': f'The page {c.get("url")} shows “{c.get("contains")}”',
                        'why': c.get('name', '')})
        elif t == 'url':
            out.append({'key': f'{i}', 'check': i, 'on': True, 'text': 'They end on a page whose address matches ' + c.get('matches', ''),
                        'why': c.get('name', '')})
        elif t == 'download':
            out.append({'key': f'{i}', 'check': i, 'on': True, 'text': 'A file is downloaded (' + c.get('matches', '') + ')',
                        'why': c.get('name', '')})
    kind = ((flow.get('engine') or {}).get('outcome') or {}).get('kind', 'change')
    return {'facts': out, 'kind': kind, 'question': ((flow.get('engine') or {}).get('outcome') or {}).get('question', ''),
            'noReset': no_reset, 'byHand': by_hand(basics)}


def stored_row(rec: dict, check: dict) -> dict:
    """The row a storage check finds, as the recording's last screen kept it in the browser."""
    from sue.target import rows_of, dig, same
    states = rec.get('states') or []
    raw = ((states[-1].get('storage') or {}) if states else {}).get(check.get('key'))
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    rows = [r for r in rows_of(data, check.get('list')) if isinstance(r, dict)]
    where = check.get('where') or {}
    hit = next((r for r in rows if all(same(dig(r, k), v) for k, v in where.items())), rows[-1] if rows else {})
    return {k: v for k, v in hit.items() if k != 'id'}


def _replace_value(flow: dict, old: str, new: str) -> None:
    """A value typed in the task, made different in every run: everywhere it appears."""
    def walk(x):
        if isinstance(x, str):
            return x.replace(old, new)
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, dict):
            return {k: walk(v) if k not in ('locate', 'explainedBy', 'route', 'id') else v for k, v in x.items()}
        return x
    flow['task'] = walk(flow['task'])
    e = flow['engine']
    e['plumbing'] = walk(e['plumbing'])
    e['target']['success'] = walk(e['target']['success'])
    e['labels'] = walk(e['labels'])
    e['words']['dataTerms'] = walk(e['words'].get('dataTerms') or [])


def unique_value(v: str) -> str:
    if '@' in v:
        local, domain = v.split('@', 1)
        return f'{local}+{{run}}@{domain}'
    return f'{v} {{run}}'


def save_facts(body) -> dict:
    """The ticks become the checks: a saved value ticked is expected, unticked is left free; any
    other check unticked is dropped. An answer can be corrected. A value made unique is a value of
    each run's own ({run}), for a product the engine cannot reset."""
    wid = body.get('id')
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    if not flow:
        raise ValueError('There is no draft yet.')
    chosen = {f['key']: f for f in body.get('facts') or [] if isinstance(f, dict) and 'key' in f}
    current = {f['key']: f for f in facts(wid)['facts']}
    checks = flow['engine']['target']['success']
    keep, unique = [], []
    for i, c in enumerate(checks):
        mine = [f for k, f in current.items() if f['check'] == i]
        if c['type'] in ('json', 'storage'):
            c['expect'] = {f['field']: f['value'] for f in mine if not f.get('fixed') and chosen.get(f['key'], f).get('on')}
            keep.append(c)
            unique += [f['value'] for f in mine if f.get('fixed') and f.get('unique') and chosen.get(f['key'], {}).get('unique')]
        else:
            f = chosen.get(str(i), mine[0] if mine else {'on': True})
            if not f.get('on', True):
                continue
            if c['type'] == 'answer' and isinstance(f.get('answer'), list) and f['answer']:
                c['expected'] = [str(a) for a in f['answer'] if str(a).strip()]
            keep.append(c)
    if not keep:
        raise ValueError('Keep at least one thing that must be right.')
    flow['engine']['target']['success'] = keep
    for value in unique:  # after the checks are set, so the checks get the run's own value too
        _replace_value(flow, value, unique_value(value))
    write_json(folder / 'flow.json', flow)
    return {'facts': facts(wid), 'problems': flow_problems(flow)}


# ---- the task, step by step, and what it takes ----------------------------------------------------------

def summary_view(wid: str) -> dict:
    """What the ready page shows: each step with its screen and what is easy to get wrong, and
    what a person needs to know, in plain words."""
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json') or {}
    rec = read_json(folder / 'recording' / 'recording.json') or {}
    states = rec.get('states') or []
    by_n = {a['n']: a for a in rec.get('actions') or []}
    steps = []
    for st in flow.get('steps') or []:
        first = by_n.get((st.get('recorded') or [None])[0])
        shot = states[first['before']]['shot'] if first and first['before'] < len(states) else None
        steps.append({'id': st['id'], 'action': st['action'], 'hard': st.get('defaults') or '', 'risky': st.get('risky'),
                      'shot': f'/wf/{wid}/{shot}' if shot else None})
    if wid in LEGACY:  # not recorded: each step on its screen from the latest full-card run
        from journey import storyboard
        for st, shot in zip(steps, storyboard(flow, RUNS)):
            st['shot'], st['shotSize'], st['shotBox'] = (shot or {}).get('url'), (shot or {}).get('size'), (shot or {}).get('box')
    know = [{'id': i['id'], 'text': i['text'], 'meaning': i.get('meaning', ''), 'kind': i['kind']}
            for i in flow.get('items') or [] if i.get('needed') and i.get('kind') != 'habit']
    traps = [{'id': i['id'], 'text': i['text']} for i in flow.get('items') or [] if i.get('kind') == 'habit']
    return {'steps': steps, 'know': know, 'traps': traps}


ADJUST = """You edit the knowledge items of a usability test workflow. Each item is something a person must know at one step
of the task (kinds: word, icon, location, concept, habit). The researcher tells you, in one sentence, what is wrong or
missing. Return JSON {"items": [...]}: the full list of items after the change. Keep every field of items you do not
change exactly as given (id, step, locate, explainedBy, exps, ...). A new item gets a new id (T plus a number not used
yet), a step id from the steps given, kind, text, meaning, needed, and exps []. Change only what the sentence asks."""


def snapshot(folder: Path) -> None:
    """The flow as it was before a change from the page, so a change can be undone."""
    if (folder / 'flow.json').exists():
        shutil.copy2(folder / 'flow.json', folder / 'flow.prev.json')


def edit_text(body) -> dict:
    """Version A's own wording, changed from its test page: the task and each step with what is
    easy to get wrong there. Ids, screens and knowledge stay as they are; the grading is the
    platform's own and is not changed here."""
    wid = body.get('id')
    if wid not in LEGACY:
        raise ValueError('Change this test from its steps instead.')
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    if 'task' in body:
        task = (body.get('task') or '').strip()
        if not 20 <= len(task) <= 4000:
            raise ValueError('Write the task as participants will read it (20 to 4,000 characters).')
        flow['task'] = task
    if 'steps' in body:
        by_id = {s['id']: s for s in flow['steps']}
        for s in body.get('steps') or []:
            step = by_id.get((s or {}).get('id'))
            if not step:
                raise ValueError('That step is not in this test.')
            action = (s.get('action') or '').strip()
            if not 3 <= len(action) <= 300:
                raise ValueError(f'Say what to do in step {flow["steps"].index(step) + 1} (3 to 300 characters).')
            step['action'], step['defaults'] = action, (s.get('hard') or '').strip()[:300]
    if 'ignored' in body:  # the checks that do not count towards "done right"
        keys = set((flow['engine'].get('grading') or {}))
        ignored = body.get('ignored') or []
        if not isinstance(ignored, list) or not set(ignored) <= keys:
            raise ValueError('That is not one of the checks.')
        if set(ignored) == keys:
            raise ValueError('Keep at least one check: without one, every run would count as done right.')
        flow['engine']['gradingIgnored'] = sorted(ignored)
    problems = flow_problems(flow)
    if problems:
        raise ValueError('That change would break the test: ' + '; '.join(problems[:3]))
    snapshot(folder)
    write_json(folder / 'flow.json', flow)
    return {'summary': summary_view(wid)}


def adjust(body) -> dict:
    """One sentence from the researcher changes what a person needs to know (Gemini), then the
    checks run again."""
    from ai_api import complete_json, settings as ai_settings
    wid, text = body.get('id'), (body.get('text') or '').strip()
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    if not flow or not 5 <= len(text) <= 1000:
        raise ValueError('Say what is wrong in a sentence.')
    prompt = (ADJUST + '\n\nSteps: ' + json.dumps([{k: s[k] for k in ('id', 'action')} for s in flow['steps']], ensure_ascii=False)
              + '\n\nItems: ' + json.dumps(flow['items'], ensure_ascii=False) + '\n\nThe researcher says: ' + text)
    result = complete_json(prompt, {'type': 'object'}, {**ai_settings(), 'json_mode': 'json_object'})
    items = result.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('The change could not be made; say it another way.')
    old = {i['id']: i for i in flow['items']}
    steps = {s['id'] for s in flow['steps']}
    merged = []
    for it in items:
        if not isinstance(it, dict) or it.get('step') not in steps or it.get('kind') not in ('word', 'icon', 'location', 'concept', 'habit'):
            continue
        base = dict(old.get(it.get('id'), {}))
        for k in ('locate', 'explainedBy'):  # where an item is on screen is never the model's to change
            it.pop(k, None)
        base.update(it)
        base.setdefault('way', None)
        base.setdefault('altOf', None)
        base.setdefault('exps', [])
        base.setdefault('basis', 'Added in review: ' + text[:120])
        base.setdefault('everyday', '')
        base.setdefault('common', 'none' if base['kind'] == 'word' else '')
        merged.append(base)
    ids = {i['id'] for i in merged}
    flow['items'] = merged
    for g in flow['knowledgeGroups']:
        g['items'] = [i for i in g['items'] if i in ids]
    owned = {i for g in flow['knowledgeGroups'] for i in g['items']}
    for it in merged:
        if it['kind'] != 'habit' and it['id'] not in owned:
            word = it['kind'] == 'word'
            g = next((g for g in flow['knowledgeGroups'] if bool(g.get('word')) == word), None)
            if not g:
                g = {'key': 'other-terms' if word else 'other-knowledge', 'title': 'Other terms' if word else 'Other knowledge',
                     'word': word, 'default': 1, 'description': 'Added in review', 'examples': '', 'items': []}
                flow['knowledgeGroups'].append(g)
            g['items'].append(it['id'])
    flow['knowledgeGroups'] = [g for g in flow['knowledgeGroups'] if g['items']]
    for k in ('entry', 'help', 'review'):
        flow['engine']['items'][k] = [i for i in flow['engine']['items'].get(k, []) if i in ids]
    problems = flow_problems(flow)
    if problems:
        raise ValueError('That change would break the workflow: ' + '; '.join(problems[:3]))
    added = sorted(ids - set(old))
    removed = sorted(set(old) - ids)
    snapshot(folder)
    write_json(folder / 'flow.json', flow)
    return {'added': added, 'removed': removed, 'changed': sum(1 for i in merged if i['id'] in old and i != old[i['id']]),
            'summary': summary_view(wid)}


# ---- a real participant's survey ---------------------------------------------------------------------

CODE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
ANSWERS = DATA / 'answers'


def save_participant(body) -> dict:
    """A card the Persona Builder built from a participant's own questionnaire answers, saved as a
    platform persona under a code name, never a full name. The record keeps the answers, the card
    as built and the editor settings it starts from, so later edits change only what they touch."""
    code, card, answers, parameters = (body.get('code') or '').strip(), body.get('card'), body.get('answers'), body.get('parameters')
    if not CODE.match(code):
        raise ValueError('Give the participant a code name: letters, digits, - or _, such as P4.')
    if not isinstance(card, dict) or card.get('format') != 'sue-persona' or card.get('version') != 2:
        raise ValueError('Send the card the Persona Builder built.')
    if card.get('flow') != current_name():
        raise ValueError('This card was built for another test; reload the page.')
    if not isinstance(answers, dict) or answers.get('kind') != 'sue-questionnaire':
        raise ValueError('Send the questionnaire answers the card was built from.')
    if not isinstance(parameters, dict):
        raise ValueError('Send the editor settings read from the card.')
    if any(p['name'].lower() == code.lower() for p in list_personas()['personas']):
        raise ValueError(f'{code} is already used; choose another code name.')
    cid = 'studio-' + uuid.uuid4().hex
    card = clone_json(card)
    card['persona'].update(id=cid, name=code)
    answers = clone_json(answers)
    answers.setdefault('answers', {})['name'] = code  # the code name only, never the person's name
    write_json(PERSONAS / f'{cid}.json', card)
    write_json(RECORDS / f'{cid}.json', {'format': 'sue-studio-record', 'version': 2, 'source': 'questionnaire', 'parameters': parameters,
                                         'baseParameters': parameters, 'baseCard': card, 'answers': answers, 'card': f'{cid}.json',
                                         'description': 'Built from their own answers about what they know and how they work.'})
    return {'id': cid, 'name': code}


def keep_answers(new: dict, base: dict, before: dict, after: dict) -> dict:
    """An edited questionnaire card: the rebuilt card for what the researcher changed, the card
    their answers built for everything else."""
    out = clone_json(new)
    flow = read_json(current_flow_path()) or {}
    groups = {g['key']: g['items'] for g in flow.get('knowledgeGroups') or []}
    changed_ids = {i for k, ids in groups.items() if (before.get('knowledge') or {}).get(k) != (after.get('knowledge') or {}).get(k) for i in ids}
    bo, ao = before.get('overrides') or {}, after.get('overrides') or {}
    changed_ids |= {i for i in set(bo) | set(ao) if bo.get(i) != ao.get(i)}

    def same(*keys):
        return all(before.get(k) == after.get(k) for k in keys)

    for k in ('risk', 'patience', 'detailFind', 'detailCheck', 'detail'):
        keys = ('detailFind', 'detailCheck') if k == 'detail' else (k,)
        if same(*keys, 'stakes') and k in (base.get('tendency') or {}) and k in out['tendency']:
            out['tendency'][k]['source'] = base['tendency'][k].get('source', out['tendency'][k].get('source'))
    if 'habit' in (base.get('tendency') or {}):
        out['tendency']['habit'] = base['tendency']['habit']
    goal = clone_json(base.get('goal') or {})
    for k, keys in (('confirmBy', ('confirmBy',)), ('ifConfirmMissing', ('ifConfirmMissing',)), ('situation', ('urgency', 'stakes'))):
        if not same(*keys):
            goal[k] = out['goal'].get(k)
    out['goal'] = goal
    persona = clone_json(base['persona'])
    persona['name'] = out['persona'].get('name') or persona['name']
    for k in ('english', 'vocabSize'):
        if not same(k):
            persona['lang'][k] = out['persona']['lang'].get(k)
            if k == 'vocabSize':
                persona['lang']['vocabSource'] = out['persona']['lang'].get('vocabSource')
    out['persona'] = persona
    out['answersFilledAt'] = base.get('answersFilledAt')
    if not changed_ids:
        for k in ('items', 'screens', 'steps'):
            out[k] = clone_json(base[k])
        return out
    base_items = {i['id']: i for i in base['items']}
    out['items'] = [i if i['id'] in changed_ids or i['id'] not in base_items else clone_json(base_items[i['id']]) for i in out['items']]
    base_words = {(s['screen'], w['id']): w for s in base['screens'] for w in s['words']}
    for screen in out['screens']:
        screen['words'] = [w if w['id'] in changed_ids or (screen['screen'], w['id']) not in base_words
                           else clone_json(base_words[(screen['screen'], w['id'])]) for w in screen['words']]
        screen['knowledge'] = [{'id': i['id'], 'kind': i['kind'], 'text': i['text'], 'level': i['result']} for i in out['items']
                               if i.get('screen') == screen['screen'] and i['kind'] not in ('word', 'habit') and i.get('result') in ('understands', 'vague')]
    return out


def clone_json(x):
    return json.loads(json.dumps(x))
