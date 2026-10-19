"""Persona Studio's local server, connected to the engine (engine-design.md 4.9, merged 2026-10-19).

Persona Studio was built by Joy (github.com/Joy0727/Persona-Studio) as an editor without the
engine. Here it saves sue-persona v3 cards straight into data/personas and runs them: Save &
Run starts `python -m sue.batch` with several seeded runs and shows what they add up to.

    engine/.venv/Scripts/python tools/persona-studio/server.py

The server listens on 127.0.0.1 only. Keys stay in engine/.env; the page never sees them.
"""
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # the engine repository: data/, tools/, engine/
ENGINE = ROOT / 'engine'
RUNS = ENGINE / 'runs'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ENGINE))
from survey_text import extract_text, read_interview_document  # noqa: E402
from persona_batch import generate_batch  # noqa: E402
from ai_api import settings as ai_settings  # noqa: E402

TOKEN = secrets.token_urlsafe(32)
STATIC = {'/': HERE / 'index.html', '/index.html': HERE / 'index.html',
          '/builder': ROOT / 'tools' / 'persona-builder.html',
          **{'/' + name: HERE / name for name in ('studio.js', 'studio.css', 'roles.js', 'parameters.js')}}
CARD_ID = re.compile(r'^studio-[0-9a-f]{32}$')
TRAITS = ('risk', 'patience', 'detailFind', 'detailCheck')


def engine_python() -> Path:
    for p in (ENGINE / '.venv' / 'Scripts' / 'python.exe', ENGINE / '.venv' / 'bin' / 'python'):
        if p.exists():
            return p
    return Path(sys.executable)


def env_keys() -> set[str]:
    path = ENGINE / '.env'
    if not path.is_file():
        return set()
    keys = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line and line.split('=', 1)[1].strip():
            keys.add(line.split('=', 1)[0].strip())
    return keys | {k for k in ('GEMINI_API_KEY', 'ADMIN_PASSWORD') if os.environ.get(k)}


def platform_url() -> str:
    from sue.config import load_config
    return load_config()['platform']['base_url']


def platform_up() -> bool:
    try:
        with urlopen(platform_url(), timeout=2) as r:
            return r.status < 500
    except Exception:  # noqa: BLE001 - any failure means not reachable
        return False


# ---- saving -------------------------------------------------------------------------

def save_card(body):
    card, parameters, answers = (body.get(key) for key in ('card', 'parameters', 'answers'))
    if not all(isinstance(v, dict) for v in (card, parameters, answers)):
        raise ValueError('A card, parameters and source answers are required.')
    if card.get('format') != 'sue-persona' or card.get('version') != 3:
        raise ValueError('Expected a sue-persona v3 card.')
    if card.get('persona', {}).get('cardType') != 'normal':
        raise ValueError('Expected a normal persona card.')
    if any(not isinstance(card.get(key), list) or not card[key] for key in ('items', 'screens', 'steps')):
        raise ValueError('The card is incomplete.')
    for key in TRAITS:
        t = card.get('tendency', {}).get(key, {})
        if t.get('level') not in ('low', 'medium', 'high') or not isinstance(t.get('score'), (int, float)) or not 0 <= t['score'] <= 10:
            raise ValueError('Invalid behavior score: ' + key)
    if not isinstance(card.get('state'), dict) or not isinstance(card.get('perception'), dict):
        raise ValueError('The card has no state or perception.')
    identity = 'studio-' + uuid.uuid4().hex
    cards, records = ROOT / 'data' / 'personas', ROOT / 'data' / 'studio-configurations'
    cards.mkdir(parents=True, exist_ok=True)
    records.mkdir(parents=True, exist_ok=True)
    target, record = cards / (identity + '.json'), records / (identity + '.json')
    try:
        with target.open('x', encoding='utf-8') as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
        with record.open('x', encoding='utf-8') as f:
            json.dump({'format': 'sue-studio-record', 'version': 2, 'parameters': parameters, 'nativeAnswers': answers,
                       'card': target.name}, f, ensure_ascii=False, indent=2)
    except Exception:
        target.unlink(missing_ok=True)
        record.unlink(missing_ok=True)
        raise
    return {'id': identity, 'filename': target.name, 'path': str(target)}


# ---- running the engine ---------------------------------------------------------------

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def active_job() -> str | None:
    with JOBS_LOCK:
        return next((jid for jid, j in JOBS.items() if j['proc'].poll() is None), None)


def start_run(body):
    card = body.get('card')
    if not isinstance(card, str) or not CARD_ID.match(card) or not (ROOT / 'data' / 'personas' / (card + '.json')).exists():
        raise ValueError('Save the card first; only cards saved by Persona Studio can be run here.')
    runs = body.get('runs', 5)
    if type(runs) is not int or not 1 <= runs <= 10:
        raise ValueError('Choose 1 to 10 runs.')
    session = body.get('likeSession') or None
    if session is not None and (not isinstance(session, str) or not re.match(r'^[A-Za-z0-9_-]{6,64}$', session)):
        raise ValueError('That is not a session id.')
    if active_job():
        raise ValueError('A run is already going. Wait for it, or stop it first.')
    if not platform_up():
        raise ValueError(f'The platform is not reachable at {platform_url()}. Start it (npm run dev) and try again.')
    RUNS.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex[:12]
    log_path = RUNS / f'studio-job-{jid}.log'
    cmd = [str(engine_python()), '-m', 'sue.batch', '--card', card, '--runs', str(runs)]
    if session:
        cmd += ['--like-session', session]
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    log = log_path.open('w', encoding='utf-8')
    proc = subprocess.Popen(cmd, cwd=ENGINE, stdout=log, stderr=subprocess.STDOUT, env=env,
                            creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    with JOBS_LOCK:
        JOBS[jid] = {'proc': proc, 'card': card, 'runs': runs, 'log': log_path, 'logfile': log, 'stopped': False,
                     'started': time.time()}
    return {'id': jid}


def batch_dir(log_text: str) -> Path | None:
    m = re.findall(r'^Saved to (.+batch-[0-9-]+)\s*$', log_text, flags=re.M)
    return Path(m[-1].strip()) if m else None


def job_status(jid):
    with JOBS_LOCK:
        job = JOBS.get(jid)
    if not job:
        raise ValueError('No such run.')
    code = job['proc'].poll()
    state = 'running' if code is None else 'stopped' if job['stopped'] else 'completed' if code == 0 else 'failed'
    if code is not None and not job['logfile'].closed:
        job['logfile'].close()
    text = job['log'].read_text(encoding='utf-8', errors='replace') if job['log'].exists() else ''
    done = len(re.findall(r'^##### ', text, flags=re.M))
    head = f'Run {min(done, job["runs"])} of {job["runs"]} ({job["card"]})\n\n' if state == 'running' else ''
    out = {'state': state, 'card': job['card'], 'log': head + text[-6000:]}
    if state == 'completed' and batch_dir(text):
        out['report'] = '/report?job=' + jid
    return out


def stop_run(body):
    jid = body.get('id')
    with JOBS_LOCK:
        job = JOBS.get(jid) if isinstance(jid, str) else None
    if not job:
        raise ValueError('No such run.')
    if job['proc'].poll() is None:
        job['stopped'] = True
        job['proc'].terminate()
    return {'stopped': True}


def report_page(jid) -> str:
    with JOBS_LOCK:
        job = JOBS.get(jid)
    if not job:
        raise ValueError('No such run.')
    folder = batch_dir(job['log'].read_text(encoding='utf-8', errors='replace'))
    if not folder or not (folder / 'batch.json').exists():
        raise ValueError('This run has no results yet.')
    data = json.loads((folder / 'batch.json').read_text(encoding='utf-8'))
    note = (folder / 'batch.md').read_text(encoding='utf-8') if (folder / 'batch.md').exists() else ''
    links = []
    for agg in data['cards']:
        for i, d in enumerate(agg['run_dirs'], 1):
            name = Path(d).name
            links.append(f'<li><a href="/runs/{html.escape(name)}/report.html" target="_blank">Run {i} (seed {agg["seeds"][i - 1]})</a></li>')
    return ('<!doctype html><meta charset="utf-8"><title>Persona Studio runs</title>'
            '<style>body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#202124}'
            'pre{white-space:pre-wrap;background:#f1f3f4;padding:14px;border-radius:8px}a{color:#1a73e8}</style>'
            f'<h1>What the runs add up to</h1><pre>{html.escape(note)}</pre><h2>Each run</h2><ul>{"".join(links)}</ul>'
            f'<p>Files: {html.escape(str(folder))}</p>')


def run_file(path: str) -> Path | None:
    """A file inside engine/runs, for the per-run reports; nothing outside it."""
    target = (RUNS / path).resolve()
    return target if RUNS.resolve() in target.parents and target.is_file() else None


# ---- vocabulary preview, with the engine's own rules ----------------------------------------

# The questionnaire's 50-word test without its made-up words (tools/persona-builder.html).
SAMPLE = ['idea', 'river', 'fire', 'brother', 'drink', 'honest', 'prevent', 'shape', 'drama', 'reasonable', 'severe',
          'poverty', 'chamber', 'experiment', 'desperate', 'recover', 'hammer', 'grief', 'beard', 'comply', 'wheat',
          'pledge', 'likelihood', 'forehead', 'vocational', 'stitch', 'rectangular', 'vapor', 'depiction', 'manageable',
          'mixer', 'prevail', 'courteous', 'copious', 'assailant', 'adrift', 'perforated', 'crackling', 'sarcophagus', 'gemstone']


def vocabulary_preview(body):
    from sue.config import load_config
    from sue.persona import CardError, persona_from_card
    from sue.words import build_vocabulary

    card, extra = body.get('card'), body.get('text') or ''
    if not isinstance(card, dict) or not isinstance(extra, str) or len(extra) > 5000:
        raise ValueError('Send a card and at most 5,000 characters of extra text.')
    config = load_config()
    try:
        vocab = build_vocabulary(persona_from_card(card, Path('studio-preview.json')), config)
    except (CardError, KeyError, TypeError) as error:
        raise ValueError(f'The card cannot be read by the engine: {error}') from None
    limit = vocab.common.limit

    def row(category, text, reason=None):
        rw = vocab.rewrite(text)
        readable = all(h.level != 'none' for h in rw.hits)
        rank = next((h.rank for h in rw.hits if h.rank), None)
        why = reason or ('Within the vocabulary limit' if readable else 'Rarer than the vocabulary limit, or unknown on the card')
        return {'category': category, 'text': text, 'readable': readable, 'states': sorted({h.level for h in rw.hits}) or ['understands'],
                'shown': rw.text, 'reason': why, 'rank': rank}

    rows = [row('50-word reference sample', w) for w in SAMPLE]
    seen = set()
    for screen in card.get('screens', []):
        for w in screen.get('words', []):
            if w['id'] in seen:
                continue
            seen.add(w['id'])
            rows.append({'category': 'Workflow terms', 'text': w['original'], 'readable': w['level'] != 'none',
                         'states': [w['level']], 'shown': w['shown'], 'reason': 'Set by the card\'s knowledge settings', 'rank': None})
    item_words = {w.lower() for s in card.get('screens', []) for w in re.findall(r'[A-Za-z]+', ' '.join(x['original'] for x in s.get('words', [])))}
    steps_text = ' '.join([card.get('goal', {}).get('task', '')] + [s.get('action', '') for s in card.get('steps', [])])
    for w in sorted({w.lower() for w in re.findall(r'[A-Za-z]{3,}', steps_text)} - item_words):
        rows.append(row('Workflow reference words', w))
    words_cfg = config['words']
    for w in words_cfg['ui_words'] + words_cfg['data_terms']:
        rows.append({'category': 'Protected data / interface', 'text': w, 'readable': True, 'states': ['understands'], 'shown': w,
                     'reason': 'Interface word or data term: always readable', 'rank': None})
    for w in sorted({w.lower() for w in re.findall(r'[A-Za-z]{2,}', extra)}):
        rows.append(row('Additional screen words', w))
    sample = [r for r in rows if r['category'] == '50-word reference sample']
    original = extra.strip() or (card.get('goal', {}).get('task', '').split('.')[0] + '.')
    return {'limit': limit, 'levelDefaults': words_cfg['top_n'], 'rows': rows,
            'sampleReadable': sum(r['readable'] for r in sample), 'sampleTotal': len(sample),
            'scope': 'Words from this workflow, the 50-word test sample, and any text you add.',
            'method': 'Each word goes through the engine\'s own vocabulary: workflow terms follow the card; other words are readable when their frequency rank is within the limit.',
            'example': {'original': original, 'shown': vocab.rewrite(original).text}}


# ---- status ----------------------------------------------------------------------------

def status():
    py, keys = engine_python(), env_keys()
    up = platform_up()
    ai = ai_settings()
    checks = [
        {'ok': (ENGINE / '.venv').exists() and py.exists(), 'label': f'Engine Python: {py}'},
        {'ok': {'GEMINI_API_KEY', 'ADMIN_PASSWORD'} <= keys, 'label': 'engine/.env has GEMINI_API_KEY and ADMIN_PASSWORD'},
        {'ok': up, 'label': f'Platform reachable at {platform_url()}' + ('' if up else ' (start it with npm run dev)')},
        {'ok': bool(ai['api_key'] and ai['model']), 'label': f'AI for interviews and batches: {ai["model"] or "not set"}'},
    ]
    return {'token': TOKEN, 'ready': all(c['ok'] for c in checks[:3]), 'activeJob': active_job(), 'checks': checks}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def send_bytes(self, data: bytes, ctype: str, status=200):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, body, status=200):
        self.send_bytes(json.dumps(body, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8', status)

    def do_GET(self):
        if not self.valid_host():
            self.send_json({'error': 'Use the local studio address.'}, 403)
            return
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == '/api/status':
                self.send_json(status())
                return
            if url.path == '/api/job':
                self.send_json(job_status((query.get('id') or [''])[0]))
                return
            if url.path == '/report':
                self.send_bytes(report_page((query.get('job') or [''])[0]).encode('utf-8'), 'text/html; charset=utf-8')
                return
            if url.path.startswith('/runs/'):
                target = run_file(url.path[len('/runs/'):])
                if target is None:
                    self.send_json({'error': 'Not found.'}, 404)
                    return
                ctype = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
                self.send_bytes(target.read_bytes(), ctype + ('; charset=utf-8' if ctype.startswith('text/') else ''))
                return
        except ValueError as error:
            self.send_json({'error': str(error)}, 400)
            return
        path = STATIC.get(url.path)
        if path is None:
            self.send_json({'error': 'Not found.'}, 404)
            return
        self.send_bytes(path.read_bytes(), (mimetypes.guess_type(str(path))[0] or 'text/plain') + '; charset=utf-8')

    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Studio-Token') != TOKEN:
            self.send_json({'error': 'Reload Persona Studio before saving.'}, 403)
            return
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            self.send_json({'error': 'Use the local studio page.'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1000000:
                raise ValueError('Invalid request size.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected an object.')
            if self.path == '/api/save':
                result = save_card(body)
            elif self.path == '/api/extract-interview':
                result = extract_text(body.get('text'), HERE / '.extraction-cache')
            elif self.path == '/api/read-interview':
                result = read_interview_document(body.get('document'))
            elif self.path == '/api/generate-batch':
                result = generate_batch(body, HERE / '.extraction-cache')
            elif self.path == '/api/vocabulary-preview':
                result = vocabulary_preview(body)
            elif self.path == '/api/run':
                result = start_run(body)
            elif self.path == '/api/stop':
                result = stop_run(body)
            else:
                self.send_json({'error': 'Unknown endpoint.'}, 404)
                return
            self.send_json(result)
        except (ValueError, KeyError, TypeError) as error:
            self.send_json({'error': str(error)}, 400)
        except OSError:
            self.send_json({'error': 'Could not access local files. Check local file permissions.'}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        if args.port != 8765:
            raise
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('Persona Studio: ' + url, flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
