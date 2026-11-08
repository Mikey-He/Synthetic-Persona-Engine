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
from datetime import datetime
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
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


def detail(wid: str) -> dict:
    folder = wf_dir(wid)
    flow = read_json(folder / 'flow.json')
    notes = (read_json(folder / 'draft-notes.json', {}) or {}).get('notes', [])
    out = summary(wid) | {'basics': read_json(folder / 'basics.json', {}) or {}, 'flow': flow, 'notes': notes, 'check': read_json(folder / 'check.json')}
    job = job_for(wid)
    out['job'] = job['id'] if job else None
    return out


# ---- jobs: run -------------------------------------------------------------------------------------

def _procs(job: dict) -> list:
    return [c['proc'] for c in job.get('children') or []] or [job['proc']]


def busy() -> dict | None:
    with LOCK:
        return next((j for j in JOBS.values() if any(p.poll() is None for p in _procs(j))), None)


def start_many(kind: str, cmds: list, **meta) -> dict:
    """One job, several engine processes side by side (one per card), so a group of six runs in the time
    of one (2026-11-08). Each child keeps its own log; the views merge them."""
    other = busy()
    if other:
        raise ValueError(f'The engine is busy ({other["kind"]} {other.get("label", "")}). Wait for it or stop it first.')
    RUNS.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex[:12]
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', SUE_FLOW=meta.pop('flow', os.environ.get('SUE_FLOW', '')))
    if not env['SUE_FLOW']:
        env.pop('SUE_FLOW')
    job = {'id': jid, 'kind': kind, 'children': [], 'pending': list(cmds), 'env': env, 'started': time.time(), 'stopped': False, **meta}
    _advance(job)
    job.update(proc=job['children'][0]['proc'], log=job['children'][0]['log'], logfile=job['children'][0]['logfile'])
    with LOCK:
        JOBS[jid] = job
    return {'id': jid}


SIDE_BY_SIDE = 6  # engines at once: each is a browser and a stream of model calls; more would slow them all


def _advance(job: dict) -> None:
    """Starts queued cards while fewer than SIDE_BY_SIDE engines run. Called when the job is started and
    whenever its state is read (the Run page polls every two seconds)."""
    if job.get('stopped'):
        job['pending'] = []
        return
    running = sum(1 for c in job['children'] if c['proc'].poll() is None)
    while job.get('pending') and running < SIDE_BY_SIDE:
        card, cmd = job['pending'].pop(0)
        n = len(job['children']) + 1
        log_path = RUNS / f"platform-{job['kind']}-{job['id']}-{n}.log"
        log = log_path.open('w', encoding='utf-8')
        proc = subprocess.Popen(cmd, cwd=ENGINE, stdout=log, stderr=subprocess.STDOUT, env=job['env'],
                                creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        job['children'].append({'card': card, 'proc': proc, 'log': log_path, 'logfile': log})
        running += 1
        time.sleep(1.2)  # the engine names a batch folder by the second


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
    if job.get('children'):
        _advance(job)
    codes = []
    for c in job.get('children') or [{'proc': job['proc'], 'logfile': job['logfile']}]:
        code = c['proc'].poll()
        if code is not None and not c['logfile'].closed:
            c['logfile'].close()
        codes.append(code)
    if any(code is None for code in codes) or job.get('pending'):
        return 'running'
    return 'stopped' if job['stopped'] else 'completed' if all(code == 0 for code in codes) else 'failed'


def get_job(jid: str) -> dict:
    with LOCK:
        job = JOBS.get(jid)
    if not job:
        raise ValueError('No such job.')
    return job


def _log_texts(job: dict) -> list:
    logs = [c['log'] for c in job.get('children') or []] or [job['log']]
    return [p.read_text(encoding='utf-8', errors='replace') if p.exists() else '' for p in logs]


def log_text(job: dict) -> str:
    return '\n'.join(_log_texts(job))


def stop_job(body) -> dict:
    job = get_job(body.get('id'))
    for proc in _procs(job):
        if proc.poll() is None:
            job['stopped'] = True
            if job['kind'] == 'record':
                (wf_dir(job['workflow']) / 'recording' / 'STOP').write_text('stop', encoding='utf-8')
            else:
                proc.terminate()
    return {'stopped': True}


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
            'group': (record or {}).get('group'), 'groupName': (record or {}).get('groupName'), 'base': (record or {}).get('base'), 'variant': (record or {}).get('variant'),
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


def group_plan(body) -> dict:
    """Variants around a base persona: Gemini plans which of the chosen settings take which values, code keeps
    the combinations distinct (persona_batch). The participants of this workflow, if any, are passed as evidence
    of plausible ranges; with none, the plan rests on the description alone and the group says so."""
    from persona_batch import generate_batch
    baseline, fields, count = body.get('baseline'), body.get('fields'), body.get('count')
    if not isinstance(baseline, dict) or not isinstance(fields, list) or not fields or type(count) is not int or not 2 <= count <= 60:
        raise ValueError('Choose 2 to 60 people and at least one setting that may differ.')
    references = []
    if body.get('useParticipants'):  # only when asked: the group is the role's, not the participants'
        for path in sorted(RECORDS.glob('studio-*.json')):
            rec = read_json(path, {}) or {}
            card = read_json(PERSONAS / path.name, {}) or {}
            if rec.get('source') in ('questionnaire', 'survey') and card.get('flow') == current_name() and rec.get('parameters'):
                references.append({'id': path.stem, 'name': rec['parameters'].get('name'), 'parameters': rec['parameters'], 'description': rec.get('description', '')})
    plan = generate_batch({'count': min(200, count * 3), 'requestedCount': count, 'fields': fields, 'instructions': body.get('instructions') or '',
                           'baseline': baseline, 'role': {'title': str(body.get('title') or baseline.get('name') or ''), 'background': str(body.get('description') or '')},
                           'references': references}, HERE / '.extraction-cache')
    plan['references'] = len(references)
    return plan


def update_record(body) -> dict:
    """A persona's record fields that are not settings: which group it belongs to, and the group's name."""
    cid = body.get('id')
    if not isinstance(cid, str) or not CARD.match(cid) or not (RECORDS / f'{cid}.json').exists():
        raise ValueError('No such persona.')
    data = read_json(RECORDS / f'{cid}.json', {}) or {}
    for key in ('group', 'groupName'):
        if key in body:
            data[key] = body[key]
    write_json(RECORDS / f'{cid}.json', data)
    return {'ok': True}


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
    # A variant made from a base persona: which group it belongs to, which card it was made from, and what
    # was changed (the base persona + small changes make up a group, which runs as one; 2026-11-08).
    for key in ('group', 'base', 'variant', 'groupName'):
        if body.get(key) is not None:
            data[key] = body[key]
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
    if status(wid)['key'] not in ('ready', 'changed'):  # one workflow; the checks step is gone from this platform
        raise ValueError('This workflow is not ready: run its checks first.')
    cards, runs = body.get('cards'), body.get('runs', 5)
    if not isinstance(cards, list) or not 1 <= len(cards) <= 60 or type(runs) is not int or not 1 <= runs <= 10:
        raise ValueError('Choose 1 to 60 personas and 1 to 10 runs each.')
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
    base = [str(engine_python()), '-m', 'sue.batch', '--flow', str(current_flow_path()), '--runs', str(runs), '--live']
    return start_many('run', [(c, base + ['--card', c]) for c in cards], workflow=wid, label=f'{len(cards)} personas', cards=cards, runs=runs,
                      flow=str(current_flow_path()), group=body.get('group'))


def _parse_run_log(text: str, done: list, current: list) -> list:
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
            current.append({'card': card, 'run': n, 'step': int(last[0]) if last else 0, 'route': last[1] if last else '',
                            'did': last[2][:140] if last else 'Opening the product'})
    return re.findall(r'^Saved to (.+batch-[0-9-]+)\s*$', text, flags=re.M)


def _merge_batches(job: dict, folders: list) -> str | None:
    """The children's result folders become one result: the group's cards together, as the Results page
    reads them. The children's folders go; their runs stay where they are."""
    if job.get('merged'):
        return job['merged']
    cards, first = [], None
    for f in folders:
        data = read_json(RUNS / Path(f).name)
        if not data:
            continue
        first = first or data
        cards += data.get('cards') or []
    if not first:
        return None
    out = RUNS / f'batch-{datetime.now():%Y%m%d-%H%M%S}'
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / 'batch.json', {**first, 'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'cards': cards, 'group': job.get('group')})
    for f in folders:
        shutil.rmtree(RUNS / Path(f).name, ignore_errors=True)
    job['merged'] = out.name
    return out.name


def run_view(job: dict) -> dict:
    done, current, batches = [], [], []
    texts = _log_texts(job)
    for text in texts:
        found = _parse_run_log(text, done, current)
        batches.append(Path(found[-1].strip()) if found else None)
    state = job_state(job)
    batch = None
    if len(texts) == 1 and batches[0]:
        batch = batches[0].name
    elif len(texts) > 1 and state == 'completed' and all(batches):
        batch = _merge_batches(job, batches)
    error = None
    if state == 'failed':
        tail = [ln for t in texts for ln in t.strip().splitlines() if ln.strip()][-3:]
        error = ' '.join(tail)[-400:]
    return {'done': done, 'current': current, 'cards': job.get('cards'), 'runs': job.get('runs'), 'batch': batch, 'error': error}


def live_view(job: dict) -> dict:
    """What the run going on now shows: its screen as it is, where the pointer is and what was
    clicked (live.json, written by the engine's LiveFeed), and its last steps."""
    dirs = [d for d in RUNS.iterdir() if d.is_dir() and re.match(r'^\d{8}-\d{6}-', d.name) and d.stat().st_mtime >= job['started'] - 2]
    if not dirs:
        return {'frame': None, 'state': None, 'steps': []}
    if job.get('children'):  # several cards side by side: watch the first one still running, steadily
        for c in job['children']:
            mine = [d for d in dirs if d.name.endswith(c['card'])]
            if c['proc'].poll() is None and mine:
                dirs = mine
                break
    d = max(dirs, key=lambda p: p.stat().st_mtime)
    steps = []
    path = d / 'steps.jsonl'
    if path.exists():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines()[-12:]:
            try:
                s = json.loads(line)
            except ValueError:
                continue
            a = s.get('action') or {}
            rule = s.get('rule') or ''
            m = re.search(r'worth ([\d.]+) against wanting ([\d.]+)', rule) or re.search(r'\(worth ([\d.]+)\)', rule)
            steps.append({'step': s['step'], 'route': s.get('route'), 'rule': rule, 'looking': s.get('looking_at'),
                          'did': f"{a.get('type', '')} {a.get('original') or a.get('text') or ''}".strip(),
                          'why': next((c.get('why') for c in s.get('candidates') or [] if c.get('element') == a.get('element')), ''),
                          'worth': m.group(1) if m else None, 'want': m.group(2) if m and m.lastindex and m.lastindex >= 2 else None,
                          'reading': s.get('task_reading'), 'settled': rule.startswith('Read everything')})
    run = read_json(d / 'run.json', {}) or {}
    state = read_json(d / 'live.json')
    frame = f'/runs/{d.name}/live.jpg' if (d / 'live.jpg').exists() else None
    if not frame:  # a run without the live feed: its newest screenshot
        shots = sorted(d.glob('step_*.png'))
        frame = f'/runs/{d.name}/{shots[-1].name}' if shots else None
    return {'dir': d.name, 'card': run.get('persona'), 'seed': run.get('seed'), 'frame': frame, 'state': state, 'steps': steps}


def billing_view() -> dict:
    """The one workflow this platform tests, read-only: the task as the participant reads it, the steps,
    the parts of the form, what must be right at the end, and where the task can be read more than one way."""
    flow = read_json(current_flow_path(), {}) or {}
    e = flow.get('engine') or {}
    readings = read_json(current_flow_path().parent / 'readings.json', {}) or {}
    return {'name': flow.get('name', ''), 'task': flow.get('task', ''), 'start': (e.get('target') or {}).get('start', ''),
            'steps': [{'id': s.get('id'), 'action': s.get('action', '')} for s in flow.get('steps') or []],
            'parts': (e.get('compare') or {}).get('parts') or [],
            'checks': [c.get('name', '') for c in (e.get('target') or {}).get('success') or []],
            'readings': [{'about': a.get('about', ''), 'options': a.get('options') or []} for a in readings.get('ambiguities') or []],
            'personas': len(list_personas()['personas'])}


# ---- the three questions, with the computation behind every number (2026-11-01) ------------------

def _people_files() -> list:
    """Participant files from the study page, wherever they are kept under data/participants."""
    out = []
    for p in sorted((ROOT / 'data' / 'participants').glob('*/participant-*.json')):
        try:
            d = read_json(p)
            if d and d.get('kind') == 'uat-participant-file':
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def _route(facts, before: str, entry_label: str) -> dict:
    clicks = [f.what for f in facts if f.kind in ('click', 'value') and f.part == before]
    create = next((i for i, w in enumerate(clicks) if w == entry_label), None)
    return {'first': clicks[0] if clicks else '', 'entry': clicks[create - 1] if create else ''}


def _saved(rows) -> dict | None:
    if not isinstance(rows, list) or not rows:
        return None
    r = rows[-1]
    return {'amount': r.get('amount'), 'rules': [f"{x.get('percent')}% {x.get('trigger')}" for x in r.get('rules') or []]}


def tables_view(bid: str) -> dict:
    """Each run and each person who did the task, read the same way: where they went first, what went
    wrong in each part, what they saved and whether it passed. The page sums it up and shows this behind
    every cell."""
    if not re.match(r'^batch-[0-9-]+$', bid or ''):
        raise ValueError('That is not a result.')
    data = read_json(RUNS / bid / 'batch.json')
    if not data:
        raise ValueError('No such result.')
    from sue.config import load_config
    from sue.events import engine_facts, person_facts, person_trouble, run_trouble
    from sue.parts import AFTER, BEFORE, engine_parts, person_parts, read_steps
    from sue.target import json_check
    config = load_config(flow=str(current_flow_path()))
    c, success = config['compare'], config['workflow']['target']['success']
    parts, commit = c.get('parts') or [], config['run'].get('commit_labels') or []
    entry_label = (c.get('entry') or ['+ CREATE BUDGET'])[0]
    storage_key = next((s.get('key') for s in success if s.get('type') == 'storage'), None)
    names = {}
    for card in data.get('cards') or []:
        p = read_json(PERSONAS / f"{card['card']}.json", {}) or {}
        names[card['card']] = (p.get('persona') or {}).get('name') or card['card']
    runs = []
    for card in data.get('cards') or []:
        for i, r in enumerate(card.get('run_dirs') or []):
            d = RUNS / Path(r).name
            s = read_json(d / 'summary.json', {}) or {}
            if not s or not (d / 'steps.jsonl').exists():
                continue
            steps = read_steps(d)
            ev = s.get('evaluation') or {}
            tr = run_trouble(str(d), s, config)
            runs.append({'card': card['card'], 'name': names[card['card']], 'n': i + 1, 'dir': d.name, 'report': f'/runs/{d.name}/report.html',
                         'passed': bool(ev.get('overall')) and (s.get('stop') or {}).get('reason') == 'completion_declared',
                         'checks': ev.get('criteria') or {}, 'stop': (s.get('stop') or {}).get('reason'),
                         'moves': engine_parts(steps, parts, commit)['moves'], 'seconds': engine_parts(steps, parts, commit)['seconds'],
                         'trouble': [list(t) for t in tr], 'saved': _saved((s.get('stored') or {}).get(storage_key)),
                         **_route(engine_facts(steps, parts, c.get('options') or {}, commit), BEFORE, entry_label)})
    people = []  # the platform reports the simulation; real people are compared outside it (2026-11-08)
    return {'id': bid, 'at': data.get('at') or bid[6:], 'parts': [BEFORE, *parts, AFTER], 'runs': runs, 'people': people, 'checks': [s.get('name') for s in success],
            'definitions': {'lost the way': f"before the form, a click that is not on the way to it (the way: {', '.join(c.get('way') or [])})",
                            'changed a value': 'the same setting given one value, then another (typing the same value again is not one)',
                            'went back': 'in the form, back to a section already passed', 'left unsaved': 'out of the form without saving, losing the work',
                            'wrong when saved': 'the saved value fails one of the checks',
                            'seconds': 'people: real time from their first click; engine: estimated from the words read and the actions made (Card, Moran and Newell), not measured'}}


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
            group = data.get('group')
            group_name = next((r.get('groupName') for r in (read_json(RECORDS / f"{c['card']}.json", {}) or {} for c in cards) if r.get('group') == group), None) if group else None
            out.append({'id': d.name, 'at': data.get('at') or d.name[6:], 'runs': runs, 'passed': sum(c.get('passed', 0) for c in cards),
                        'cards': [c['card'] for c in cards], 'group': group, 'groupName': group_name})
    return {'workflow': name, 'results': out[:50]}


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


ADJUST = """You edit the knowledge items of a usability test workflow. Each item is something a person must know at one step
of the task (kinds: word, icon, location, concept, habit). The researcher tells you, in one sentence, what is wrong or
missing. Return JSON {"items": [...]}: the full list of items after the change. Keep every field of items you do not
change exactly as given (id, step, locate, explainedBy, exps, ...). A new item gets a new id (T plus a number not used
yet), a step id from the steps given, kind, text, meaning, needed, and exps []. Change only what the sentence asks."""


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
    built, post_task = body.get('built'), body.get('postTask')
    if built is not None and (not isinstance(built, dict) or built.get('format') != 'sue-persona' or built.get('version') != 3):
        raise ValueError('Send the v3 card built from the settings.')
    if any(p['name'].lower() == code.lower() for p in list_personas()['personas']):
        raise ValueError(f'{code} is already used; choose another code name.')
    cid = 'studio-' + uuid.uuid4().hex
    card = clone_json(card)
    card['persona'].update(id=cid, name=code)
    # A participant file from the testing platform (2026-10-27): every answer reaches the engine, so the
    # card is v3, with what their answers decided item by item kept from the Persona Builder's card.
    run_card = keep_answers(built, card, parameters, parameters) if built else card
    run_card['persona'].update(id=cid, name=code)
    seen = body.get('window')
    if isinstance(seen, dict) and all(isinstance(seen.get(k), int) and seen[k] > 0 for k in ('width', 'height')):
        run_card['persona']['window'] = {'width': seen['width'], 'height': seen['height']}  # the page they saw
    answers = clone_json(answers)
    answers.setdefault('answers', {})['name'] = code  # the code name only, never the person's name
    write_json(PERSONAS / f'{cid}.json', run_card)
    write_json(RECORDS / f'{cid}.json', {'format': 'sue-studio-record', 'version': 2, 'source': 'questionnaire', 'parameters': parameters,
                                         'baseParameters': parameters, 'baseCard': card, 'answers': answers, 'card': f'{cid}.json',
                                         **({'postTask': post_task} if post_task else {}),
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
