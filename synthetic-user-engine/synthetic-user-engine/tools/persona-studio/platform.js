/* The platform (engine-design.md 6.3): workflows, personas, runs and results, on the local server.
   The look is the approved prototype's (prototype.html); everything here is real. */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = x => JSON.parse(JSON.stringify(x));

/* ---------------- talking to the server ---------------- */
let token = '';
async function api(url, body) {
  const res = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Studio-Token':token}, body:JSON.stringify(body)});
  const data = await res.json().catch(() => ({error:`The server answered ${res.status}.`}));
  if (!res.ok) throw Error(data.error || `Request failed (${res.status}).`);
  return data;
}
let snackTimer;
function snack(text, undo) {
  clearTimeout(snackTimer);
  $('#snack-text').textContent = text;
  const btn = $('#snack-action'); btn.hidden = !undo; btn.onclick = () => { undo(); $('#snack').classList.remove('show'); };
  $('#snack').classList.add('show');
  snackTimer = setTimeout(() => $('#snack').classList.remove('show'), undo ? 6000 : 4500);
}
const fail = e => { console.error(e); snack(e.message || String(e)); };
function confirmBox(title, text, yes = 'OK') {
  return new Promise(resolve => {
    $('#confirm-title').textContent = title; $('#confirm-text').textContent = text; $('#confirm-yes').textContent = yes;
    const d = $('#confirm-dialog');
    const done = v => { d.close(); resolve(v); };
    $('#confirm-yes').onclick = () => done(true); $('#confirm-no').onclick = () => done(false);
    d.show();
  });
}

/* ---------------- state ---------------- */
const S = {workflows: [], current: null, flow: null, personas: [], selfTest: [], results: [], builder: null, runJob: null};
const COLORS = [['#d3e3fd','#041e49'],['#c4eed0','#072711'],['#ffdeac','#2a1800'],['#f9dedc','#410e0b'],['#e8def8','#1d192b']];
const hash = s => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const currentWf = () => S.workflows.find(w => w.id === S.current);

/* ---------------- personas: words and helpers ---------------- */
const TRAITS = [
  {key:'risk', title:'Willingness to try unfamiliar things', low:'Avoids anything unclear; goes back or gives up', mid:'Looks for help first, then tries', high:'Clicks to see what happens'},
  {key:'patience', title:'Patience', low:'Gives up after about 3 wrong turns', mid:'Keeps going for about 6 wrong turns', high:'Keeps trying for about 10'},
  {key:'detailFind', title:'Reading pages', low:'Clicks the first thing that looks right', mid:'Skims the main parts first', high:'Reads the whole page first'},
  {key:'detailCheck', title:'Checking forms', low:'Leaves defaults they were not asked to change', mid:'Fixes what conflicts with the task', high:'Checks every field before saving'},
];
const STATES = [
  {key:'fatigue', title:'Gets tired', note:'Carefulness and patience fall as the task goes on.'},
  {key:'distraction', title:'Gets distracted', note:'Sometimes misses a small element on the screen.'},
  {key:'timePressure', title:'Time pressure', note:'Reads less, takes more risks, gives up sooner.'},
];
const PERCEPTION = [['vision','reduced','visibility','Has trouble reading small text'],['colorVision','reduced','palette',"Can't rely on colour"],
  ['clickPrecision','low','ads_click','Sometimes misses small targets'],['warningAttention','low','warning','Often misses warnings']];
const WAYS = [['action','Once they click the last button'],['list','Checking the list or details page'],['toast','A success message'],
  ['external','An email or notification'],['test','Making it actually work once']];
function initials(name) { return (String(name).match(/[\p{L}\p{N}]+/gu) || []).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?'; }
function when(at) { const m = String(at || '').match(/^(\d{4})-?(\d{2})-?(\d{2})[ T-]?(\d{2}):?(\d{2})/); if (!m) return at || '';
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]); return d.toLocaleString(undefined, {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}); }
function avatar(p, size = 48) { const [bg, fg] = COLORS[hash(p.id) % COLORS.length]; return `<span class="pav" style="background:${bg};color:${fg};width:${size}px;height:${size}px;font-size:${size*.38}px">${esc(initials(p.name))}</span>`; }
function level(t, score) { return score < 2.5 ? t.low : score < 7.5 ? t.mid : t.high; }
function readout(t, score) {
  if (score === 0 || score === 5 || score === 10) return level(t, score);
  const lower = score < 5 ? t.low : t.mid, upper = score < 5 ? t.mid : t.high;
  const lowShare = score < 5 ? (5 - score) / 5 : (10 - score) / 5;
  const [usual, sometimes] = lowShare >= 0.5 ? [lower, upper] : [upper, lower];
  return `Usually: ${usual.charAt(0).toLowerCase() + usual.slice(1)}. Sometimes: ${sometimes.charAt(0).toLowerCase() + sometimes.slice(1)}.`;
}
function chipsFor(scores, known, factors = {}) {
  const out = [];
  if (scores.detailCheck < 5) out.push(['amber','visibility_off','Skims defaults']);
  if (scores.detailCheck >= 7.5) out.push(['green','fact_check','Checks every field']);
  if (scores.risk >= 7.5) out.push(['blue','ads_click','Clicks to explore']);
  if (scores.timePressure >= 5) out.push(['amber','timer','In a hurry']);
  if (scores.distraction >= 5) out.push(['','notifications_active','Easily distracted']);
  if (scores.fatigue >= 5) out.push(['','bedtime','Gets tired']);
  if (known >= 0.9) out.push(['blue','school','Knows the product']);
  if (known <= 0.1) out.push(['','help','New to the product']);
  if (factors.vision === 'reduced') out.push(['','visibility','Small text is hard']);
  return out.slice(0, 2).map(([c, i, t]) => `<span class="tag ${c}"><span class="ms">${i}</span>${t}</span>`).join('');
}
const KIND_LABEL = {studio: 'From a description', questionnaire: "From a participant's questionnaire", survey: "From a participant's survey or interview"};
const kindLabel = p => KIND_LABEL[p.from || p.kind] || '';
/* A setting's name as the researcher knows it, for the list of what the survey did not say. */
function settingName(path) {
  const [head, key] = path.split('.');
  if (head === 'knowledge') return 'What they know: ' + ((groupsVisible().find(g => g.key === key) || {}).title || key);
  if (head === 'humanFactors') return ({vision: 'Reading small text', colorVision: 'Colour vision', clickPrecision: 'Clicking small targets',
    readingSpeed: 'Reading speed', warningAttention: 'Noticing warnings', stressTolerance: 'Coping with stress', pressureChange: 'How pressure builds',
    care: 'What they care about most', financialRiskJudgment: 'Judging financial risk', financialCaution: 'Caution with money'})[key] || key;
  const t = [...TRAITS, ...STATES].find(x => x.key === path);
  return t ? t.title : ({english: 'English level', vocabSize: 'Vocabulary size', confirmBy: 'How they make sure it is done',
    ifConfirmMissing: 'What they do if no confirmation comes', urgency: 'Urgency', stakes: 'Stakes'})[path] || path;
}
function personaCard(p) {
  return `<div class="card pcard" data-open="${esc(p.id)}">
    <div class="row" style="padding-right:36px">${avatar(p)}<div style="min-width:0"><h3>${esc(p.name)}</h3><div class="muted small">${kindLabel(p)}</div></div></div>
    <p class="muted">${esc(p.description)}</p>
    <div class="chips">${chipsFor(p.scores, p.known, (p.parameters || {}).humanFactors)}</div>
    <md-icon-button data-remove="${esc(p.id)}" aria-label="Delete persona" style="position:absolute;top:8px;right:8px"><span class="ms">delete</span></md-icon-button>
  </div>`;
}
function newCard() {
  return `<button class="card tonal pcard" data-go="new" style="display:grid;place-items:center;min-height:200px;border:0;font:inherit;color:inherit">
    <span style="text-align:center"><span class="ms" style="font-size:36px;color:var(--md-sys-color-primary)">add_circle</span><h3 style="margin-top:8px">New persona</h3></span></button>`;
}
function statusChip(st) {
  const icon = {ready:'check_circle', failed:'error', recording:'radio_button_checked', drafting:'auto_awesome', checking:'progress_activity'}[st.key] || 'schedule';
  return `<span class="chip-status ${esc(st.key)}"><span class="ms">${icon}</span>${esc(st.label)}</span>`;
}

/* ---------------- loading ---------------- */
async function loadWorkflows() {
  const data = await api('/api/workflows');
  S.workflows = data.workflows; S.current = data.current;
  const w = currentWf();
  $('#workflow-label').textContent = w ? w.name : 'Choose a workflow';
}
async function loadPersonas() { const d = await api('/api/personas'); S.personas = d.personas; S.selfTest = d.selfTest; }
async function loadResults() { S.results = (await api('/api/results')).results; }
async function loadFlow() { S.flow = (await api(`/api/workflow?id=${encodeURIComponent(S.current)}`)).flow; }
function waitBuilder() {
  return new Promise(resolve => {
    const frame = $('#builder');
    const ready = () => { const b = frame.contentWindow && frame.contentWindow.__sueBuilder; if (b) { S.builder = b; resolve(b); return true; } return false; };
    if (ready()) return;
    frame.addEventListener('load', () => { if (!ready()) setTimeout(ready, 300); });
    setTimeout(() => ready() || resolve(null), 8000);
  });
}

/* ---------------- pages ---------------- */
const pages = {};
pages.home = async () => {
  await Promise.all([loadPersonas(), loadResults()]);
  const w = currentWf(), ready = w && w.status.key === 'ready';
  const latest = S.results[0];
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  let insight = '<p class="insight">No test has run on this workflow yet.</p><p class="muted" style="margin:0 0 16px">Describe who you are testing with, then run a test.</p>';
  if (latest) {
    const failed = latest.runs - latest.passed;
    insight = `<span class="small muted">Latest result · ${esc(when(latest.at))}</span>
      <p class="insight">${failed ? `${failed} of ${latest.runs} runs did not finish the task correctly.` : `All ${latest.runs} runs finished the task correctly.`}</p>
      <md-filled-tonal-button data-go="result/${latest.id}">See the results<span slot="icon" class="ms">arrow_forward</span></md-filled-tonal-button>`;
  }
  // The first thing to do is say who to test with, so the page opens on that box.
  return `<div class="page">${composerHTML(hello)}<div id="draft-area"></div>
    <div class="hello" style="margin-top:48px;grid-template-columns:1fr">
      <div class="card tonal">${insight}
        <div class="muted small" style="margin-top:8px">Testing <b>${esc((w || {}).name || 'no task yet')}</b>${ready ? '' : ' · not ready yet'} · <a href="#tests">Tests</a></div></div>
    </div>
    ${S.personas.length ? `<h2 style="margin:32px 0 16px">Your personas</h2><div class="grid">${S.personas.map(personaCard).join('')}</div>` : ''}
  </div>`;
};

/* ---- the product details form (Advanced settings) ---- */
function basicsForm(b = {}) {
  const login = b.login || {};
  return `<div class="form">
    <md-outlined-text-field id="b-name" label="Name" value="${esc(b.name)}" supporting-text="For example: Teamspace · invite a member"></md-outlined-text-field>
    <div class="two"><md-outlined-text-field id="b-product" label="Product" value="${esc(b.product)}"></md-outlined-text-field>
      <md-outlined-text-field id="b-users" label="Who uses it" value="${esc(b.users)}"></md-outlined-text-field></div>
    <md-outlined-text-field id="b-start" label="Start page address" value="${esc(b.start)}" supporting-text="Where the task starts, e.g. https://staging.example.com/home. Never a live product: the engine really clicks Save."></md-outlined-text-field>
    <md-outlined-text-field id="b-task" type="textarea" rows="5" label="The task, as participants read it" value="${esc(b.task)}"></md-outlined-text-field>
    <div class="card tonal" style="padding:16px">
      <div class="row" style="justify-content:space-between"><div><h3>Sign-in</h3><p class="muted small" style="margin:4px 0 0">The engine signs in by itself before each run, with a test account.</p></div>
        <md-switch id="b-login-on" ${login.url ? 'selected' : ''} aria-label="The product needs a sign-in"></md-switch></div>
      <div id="b-login" class="form" style="margin-top:16px" ${login.url ? '' : 'hidden'}>
        <md-outlined-text-field id="b-login-url" label="Sign-in page" value="${esc(login.url || '/login')}"></md-outlined-text-field>
        <div class="two"><md-outlined-text-field id="b-login-user" label="Test account" ${login.user ? 'placeholder="Kept in engine/.env"' : ''}></md-outlined-text-field>
          <md-outlined-text-field id="b-login-pass" label="Password" type="password" ${login.user ? 'placeholder="Kept in engine/.env"' : ''}></md-outlined-text-field></div>
        <p class="hint">Stored only in engine/.env on this computer. Leave empty to keep the one saved.</p>
      </div>
    </div>
    <details class="more"><summary><h3>Start clean every time</h3><span class="ms">expand_more</span></summary>
      <md-outlined-text-field id="b-reset" label="Reset address (optional)" value="${esc(b.reset)}" style="margin-top:12px" supporting-text="A path the engine sends POST to before each run, e.g. /api/reset, so earlier runs leave nothing behind."></md-outlined-text-field>
    </details>
  </div>`;
}
function readBasics() {
  const v = id => ($(id) || {}).value || '';
  const out = {name: v('#b-name'), product: v('#b-product'), users: v('#b-users'), start: v('#b-start'), task: v('#b-task'), reset: v('#b-reset')};
  if ($('#b-login-on').selected) out.login = {url: v('#b-login-url'), user: v('#b-login-user'), password: v('#b-login-pass')};
  return out;
}
/* ---- Advanced settings: every part of a test's flow, for review by hand ---- */
const W = {id: null, d: null, edit: null, dirty: false, tab: 0, stepState: {}, picking: null, poll: null};
pages.workflow = async (id) => {
  W.id = id; clearTimeout(W.poll);
  W.d = await api(`/api/workflow?id=${encodeURIComponent(id)}`);
  if (!W.dirty || !W.edit || W.edit.__id !== id) { W.edit = W.d.flow ? clone(W.d.flow) : null; if (W.edit) W.edit.__id = id; W.dirty = false; }
  const d = W.d, st = d.status.key;
  if (!d.legacy && (d.job || ['new', 'recorded', 'recording', 'drafting'].includes(st))) { location.hash = 'test/' + id; return ''; }
  const head = `<a class="backlink" href="#${d.legacy ? 'tests' : 'test/' + esc(id)}"><span class="ms">arrow_back</span>${d.legacy ? 'Tests' : 'Back to the test'}</a>
    <div class="page-head"><div><div class="row" style="flex-wrap:wrap"><h1>${esc(d.name)}</h1>${statusChip(d.status)}</div>
      <p class="muted">${esc(d.product || (d.kind === 'uat' ? 'On our own test platform' : d.start))}</p></div>
      <div class="actions">${headActions(d)}</div></div>`;
  let body;
  if (d.job || ['recording','drafting','checking'].includes(st)) body = jobCard(d);
  else if (st === 'new') body = recordCard(d);
  else if (st === 'recorded') body = draftCard(d);
  else body = review(d);
  if (d.job) setTimeout(() => pollJob(d.job), 500);
  return `<div class="page">${head}${body}</div>`;
};
function headActions(d) {
  const st = d.status.key, out = [];
  if (d.legacy) return st === 'ready' && !d.current ? '<md-filled-button data-act="use-wf"><span slot="icon" class="ms">play_arrow</span>Test this workflow</md-filled-button>' : '';
  if (['draft','changed','failed','ready'].includes(st)) {
    out.push('<md-outlined-button data-act="edit-basics"><span slot="icon" class="ms">tune</span>Product details</md-outlined-button>');
  }
  if (st === 'ready' && !d.current) out.push('<md-filled-button data-act="use-wf"><span slot="icon" class="ms">play_arrow</span>Test this workflow</md-filled-button>');
  return out.join('');
}
function recordCard(d) {
  return `<div class="card"><h2>Do the task once</h2>
    <p class="muted" style="max-width:640px">A browser window opens on ${esc(d.basics.start)}${d.basics.login ? ', already signed in' : ''}. Do the task the way it should be done, at an ordinary pace.
      Open any help you think a person would need. Every click and every box you fill is written down with a screenshot; passwords never are.
      Close the window or press Finish here when you are done.</p>
    <div class="actions" style="justify-content:flex-start"><md-filled-button data-act="record"><span slot="icon" class="ms">radio_button_checked</span>Open the browser and record</md-filled-button>
      <md-text-button data-act="edit-basics">Change the details</md-text-button></div></div>`;
}
function draftCard(d) {
  const r = d.recording || {actions: [], states: []};
  return `<div class="card"><h2>Recorded: ${r.actions.length} actions on ${r.states.length} screens</h2>
    <p class="muted">Gemini drafts the steps, what a person needs to know at each one, the questionnaire and the success checks. You review every part next.</p>
    <div class="rec-list">${r.actions.map(actionLine).join('')}</div>
    <div class="actions" style="justify-content:flex-start;margin-top:16px"><md-filled-button data-act="draft"><span slot="icon" class="ms">auto_awesome</span>Draft the workflow</md-filled-button>
      <md-text-button data-act="record">Record again</md-text-button></div></div>`;
}
function actionLine(a) {
  const what = a.action === 'type' ? (a.secret ? 'Typed a password' : `Typed “${esc(a.value)}” into <b>${esc(a.name || (a.control || {}).text || '')}</b>`)
    : a.action === 'select' ? `Chose “${esc(a.value)}” in <b>${esc(a.name || (a.control || {}).text)}</b>` : a.action === 'press' ? 'Pressed Enter'
    : `Clicked <b>${esc(a.name || (a.control || {}).text || (a.control || {}).label || 'a control')}</b>`;
  return `<div><span class="tag">${a.n}</span><span>${what}</span>${a.route ? `<span class="muted small" style="margin-left:auto">${esc(a.route)}</span>` : ''}</div>`;
}
function jobCard(d) {
  const st = d.status.key;
  if (st === 'recording') return `<div class="card"><div class="row"><span class="ms" style="color:var(--md-sys-color-error)">radio_button_checked</span><h2>Recording in the browser window</h2></div>
    <p class="muted">Do the task there. Each action shows up here as it is written down.</p>
    <div class="rec-list" id="rec-live"><div class="muted">Waiting for the first action…</div></div>
    <div class="actions" style="justify-content:flex-start;margin-top:16px"><md-filled-button data-act="stop-job"><span slot="icon" class="ms">stop</span>Finish recording</md-filled-button></div></div>`;
  if (st === 'drafting') return `<div class="drafting card tonal" style="max-width:none;margin:0"><div class="row"><md-circular-progress indeterminate style="--md-circular-progress-size:28px"></md-circular-progress>
    <span>Drafting the workflow from your recording… this takes about a minute.</span></div>
    <div class="shimmer" style="width:90%;margin-top:20px"></div><div class="shimmer" style="width:70%"></div><div class="shimmer" style="width:80%"></div></div>`;
  return `<div class="card"><div class="row"><md-circular-progress indeterminate style="--md-circular-progress-size:28px"></md-circular-progress><h2>Checking the workflow</h2></div>
    <p class="muted">The engine follows your recorded path with a card that knows everything, then with one that knows nothing. It signs in, clicks and grades exactly as in a test.</p>
    <div class="checklist" id="check-live"></div>
    <div class="actions" style="justify-content:flex-start"><md-text-button data-act="stop-job">Stop</md-text-button></div></div>`;
}
async function pollJob(jid) {
  clearTimeout(W.poll);
  if (!location.hash.startsWith('#workflow/')) return;
  try {
    const j = await api(`/api/wjob?id=${jid}`);
    if (j.kind === 'record' && $('#rec-live')) $('#rec-live').innerHTML = j.view.actions.length ? j.view.actions.map(actionLine).join('') : '<div class="muted">Waiting for the first action…</div>';
    if (j.kind === 'check' && $('#check-live')) $('#check-live').innerHTML = (j.view.lines || []).map(l => `<div class="crow"><span class="ms">${/\[pass\]/.test(l) ? 'check_circle' : /FAIL/.test(l) ? 'error' : 'pending'}</span><span>${esc(l.replace(/^\s*\[\w+\]\s*/, ''))}</span><span></span></div>`).join('')
      + (j.view.started || []).map(c => `<div class="crow"><span class="ms">pending</span><span>Ran the ${esc(c)} card</span><span></span></div>`).join('');
    if (j.state === 'running') { W.poll = setTimeout(() => pollJob(jid), 1200); return; }
    if (j.kind === 'record' && j.state !== 'failed') {
      const d = await api(`/api/workflow?id=${encodeURIComponent(W.id)}`);
      if ((d.recording || {}).actions && d.recording.actions.length) { snack(`Recorded ${d.recording.actions.length} actions. Drafting now.`); await api('/api/workflows/draft', {id: W.id}); }
    } else if (j.kind === 'draft' && j.state === 'completed') { W.dirty = false; W.edit = null; snack('Drafted. Review each part, then confirm.'); }
    else if (j.kind === 'check' && j.state === 'completed') snack('Every check passed. The workflow is ready for testing.');
    else if (j.state === 'failed') snack(`${j.kind === 'check' ? 'Some checks failed' : 'That did not work'}: ${(j.log || '').trim().split('\n').slice(-1)[0].slice(0, 160)}`);
    render();
  } catch (e) { fail(e); }
}

/* -- review: the draft, part by part -- */
const KINDS = [['word','A word on screen'],['icon','An icon'],['location','Where something is'],['concept','How something works'],['habit','A habit from other products']];
function review(d) {
  const f = W.edit;
  if (!f) return '<div class="card">This workflow has no flow yet.</div>';
  const notes = (d.notes || []).filter(n => !n.startsWith('Engine:'));
  const problems = d.problems || [];
  return `${problems.length ? `<div class="banner bad"><span class="ms">error</span><div><b>Fix before checking</b><ul>${problems.slice(0, 8).map(p => `<li>${esc(p)}</li>`).join('')}</ul></div></div>` : ''}
    ${notes.length && d.status.key === 'draft' ? `<div class="banner"><span class="ms">rate_review</span><div><b>Look at these in the draft</b><ul>${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul></div></div>` : ''}
    ${checkCard(d)}
    <div class="tabs-wrap"><md-tabs id="wf-tabs" active-tab-index="${W.tab}"><md-primary-tab>Steps</md-primary-tab><md-primary-tab>Knowledge</md-primary-tab><md-primary-tab>Questionnaire</md-primary-tab><md-primary-tab>Success</md-primary-tab><md-primary-tab>Product</md-primary-tab></md-tabs></div>
    <div id="wf-body">${reviewTab(W.tab)}</div>
    <div class="card tonal" style="margin-top:24px;position:sticky;bottom:12px;z-index:4;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <span id="dirty-note" class="muted small" style="flex:1">${W.dirty ? 'Unsaved changes' : d.status.key === 'ready' ? 'Checked and ready. Any change asks for the checks again.' : 'Review every tab, then confirm.'}</span>
      ${d.legacy ? '' : `<md-outlined-button data-act="redraft"><span slot="icon" class="ms">auto_awesome</span>Draft again</md-outlined-button>
      <md-outlined-button data-act="save-flow" ${W.dirty ? '' : 'disabled'} id="save-flow">Save</md-outlined-button>
      <md-filled-button data-act="confirm-flow"><span slot="icon" class="ms">verified</span>Confirm and check</md-filled-button>`}
    </div>`;
}
function checkCard(d) {
  const c = d.check;
  if (!c) return '';
  const fresh = d.status.key === 'ready' || d.status.key === 'failed';
  return `<div class="card" style="margin-bottom:16px"><div class="row" style="justify-content:space-between;flex-wrap:wrap"><h3>Checks${fresh ? '' : ' (before your last change)'}</h3><span class="muted small">${esc(when(c.at))}</span></div>
    <div class="checklist">${c.checks.map(x => `<div class="crow"><span class="ms ${x.ok ? 'ok' : x.required ? 'bad' : ''}">${x.ok ? 'check_circle' : x.required ? 'error' : 'warning'}</span>
      <div><div>${esc(x.name)}</div><div class="muted small">${esc(x.detail)}</div></div>
      ${x.run ? `<md-text-button href="/runs/${esc(x.run.split(/[\\/]/).pop())}/report.html" target="_blank">See the run</md-text-button>` : '<span></span>'}</div>`).join('')}</div></div>`;
}
function reviewTab(i) { return [stepsTab, knowledgeTab, questionnaireTab, successTab, productTab][i](); }
function markDirtyFlow() {
  W.dirty = true;
  const b = $('#save-flow'); if (b) b.disabled = false;
  const n = $('#dirty-note'); if (n) n.textContent = 'Unsaved changes';
}
function routeOfScreen(sid) { return ((W.edit.screens || []).find(s => s.id === sid) || {}).route; }

/* locators, as sue/locate.py and page_script.js read them */
const normT = t => String(t || '').replace(/\s+/g, ' ').trim().toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
function sameT(h, w, how) { h = normT(h); w = normT(w); if (!w) return false; return how === 'contains' ? h.includes(w) : how === 'starts' ? h.startsWith(w) : h === w; }
function fitsLoc(c, loc, how) {
  how = how || loc.match || 'exact';
  if (loc.role && c.role !== loc.role) return false;
  if (loc.text && !sameT(c.text, loc.text, how)) return false;
  if (loc.label && !sameT(c.label, loc.label, how)) return false;
  if (loc.region && c.region !== loc.region) return false;
  if (loc.group && !sameT(c.group, loc.group)) return false;
  return true;
}
function findLoc(controls, loc) {
  if (!loc || loc.selector) return [];
  let found = controls.map((c, i) => fitsLoc(c, loc) ? i : -1).filter(i => i >= 0);
  if (!found.length && (loc.match || 'exact') === 'exact' && (loc.text || loc.label)) {
    const loose = controls.map((c, i) => fitsLoc(c, loc, 'contains') ? i : -1).filter(i => i >= 0);
    found = loose.length === 1 || loc.nth != null ? loose : [];
  }
  return loc.nth != null ? found.slice(loc.nth, loc.nth + 1) : found;
}
function sameControl(a, b) {
  return ['tag','role','text','label','region','group'].every(k => (a[k] || '') === (b[k] || '')) && Math.abs((a.box || {}).x - (b.box || {}).x) < 4 && Math.abs((a.box || {}).y - (b.box || {}).y) < 40;
}
const locText = l => !l ? 'Not tied to a control' : l.selector ? `CSS ${l.selector}` : [l.text ? `“${l.text}”` : '', l.label ? `icon “${l.label}”` : '', l.role || '', l.region ? `in ${l.region}` : '', l.group ? `under ${l.group}` : '', l.nth != null ? `#${l.nth + 1}` : ''].filter(Boolean).join(' ');

function stepStates(step) {
  const rec = W.d.recording; if (!rec) return [];
  const acts = (step.recorded || []).map(n => rec.actions.find(a => a.n === n)).filter(Boolean);
  const ns = [...new Set([...acts.map(a => a.before), ...(acts.length ? [acts[acts.length - 1].after] : [])])];
  if (!ns.length) { const route = routeOfScreen(step.screen); const s = rec.states.find(x => x.route === route); if (s) ns.push(s.n); }
  return ns;
}
function shotBox(step) {
  const rec = W.d.recording, ns = stepStates(step);
  if (!rec || !ns.length) return '<div class="muted small">No recorded screen for this step.</div>';
  const n = W.stepState[step.id] ?? ns[0], st = rec.states[n];
  const W0 = (st.size || {}).w || 1440, H0 = (st.size || {}).h || 900;
  const box = (c, cls, label, extra = '') => { const b = c.box || {}; return `<div class="${cls}" ${extra} style="left:${b.x / W0 * 100}%;top:${b.y / H0 * 100}%;width:${Math.max(b.w, 6) / W0 * 100}%;height:${Math.max(b.h, 6) / H0 * 100}%">${label ? `<span class="tagno">${esc(label)}</span>` : ''}</div>`; };
  let hits = '';
  if (W.picking && W.picking.step === step.id) {
    hits = st.controls.map((c, i) => box(c, 'pickable', '', `data-pick-state="${n}" data-pick-control="${i}" title="${esc(c.text || c.label || c.role)}"`)).join('');
  } else {
    const acts = (step.recorded || []).map(k => rec.actions.find(a => a.n === k)).filter(a => a && a.before === n);
    for (const a of acts) { const i = st.controls.findIndex(c => sameControl(c, a.control || {})); if (i >= 0) hits += box(st.controls[i], 'hit', a.n); }
    for (const it of W.edit.items.filter(x => x.step === step.id && x.locate)) for (const i of findLoc(st.controls, it.locate)) hits += box(st.controls[i], 'hit item', it.id);
  }
  return `<div class="shotscroll"><div class="shotbox ${W.picking && W.picking.step === step.id ? 'picking' : ''}"><img src="/wf/${W.id}/${st.shot}" alt="Screen ${n}: ${esc(st.route)}" loading="lazy">${hits}</div></div>
    <div class="statepick">${ns.map(k => `<button data-state-of="${step.id}" data-state="${k}" class="${k === n ? 'on' : ''}">Screen ${k} · ${esc(rec.states[k].route)}</button>`).join('')}</div>
    ${W.picking && W.picking.step === step.id ? `<div class="banner info" style="margin-top:8px"><span class="ms">touch_app</span><div>Click the control <b>${esc(W.picking.item)}</b> is about. <a href="#" data-act="cancel-pick">Cancel</a></div></div>` : ''}`;
}
function itemRow(it) {
  const word = it.kind === 'word';
  return `<div class="itemrow" data-item="${esc(it.id)}">
    <div><span class="idtag">${esc(it.id)}</span>
      <md-outlined-select data-field="kind" aria-label="Kind" style="margin-top:6px;width:100%">${KINDS.map(([k, l]) => `<md-select-option value="${k}" ${it.kind === k ? 'selected' : ''}><div slot="headline">${l}</div></md-select-option>`).join('')}</md-outlined-select></div>
    <div class="fields">
      <md-outlined-text-field data-field="text" label="${word ? 'The word, as on screen' : 'What a person needs to know'}" value="${esc(it.text)}"></md-outlined-text-field>
      <md-outlined-text-field data-field="meaning" label="What it means here" value="${esc(it.meaning)}"></md-outlined-text-field>
      ${word ? `<div class="two" style="display:grid;grid-template-columns:1fr 160px;gap:8px"><md-outlined-text-field data-field="everyday" label="Its everyday meaning, if different" value="${esc(it.everyday)}"></md-outlined-text-field>
        <md-outlined-select data-field="common" label="In everyday English">${[['common','Common'],['rare','Rare'],['none','Jargon']].map(([k, l]) => `<md-select-option value="${k}" ${it.common === k ? 'selected' : ''}><div slot="headline">${l}</div></md-select-option>`).join('')}</md-outlined-select></div>` : ''}
      <div class="where"><span class="ms" style="font-size:16px">my_location</span>${esc(locText(it.locate))}${it.explainedBy ? ` · explained by “${esc(it.explainedBy.text)}”` : ''}</div>
    </div>
    <div class="tools">
      <label class="row small" style="gap:4px"><md-checkbox data-field="needed" ${it.needed ? 'checked' : ''} aria-label="Needed to finish"></md-checkbox>Needed</label>
      <md-icon-button data-act="pick" data-item-id="${esc(it.id)}" title="Point at its control"><span class="ms">ads_click</span></md-icon-button>
      ${it.locate ? `<md-icon-button data-act="unpick" data-item-id="${esc(it.id)}" title="Not tied to a control"><span class="ms">link_off</span></md-icon-button>` : ''}
      <md-icon-button data-act="del-item" data-item-id="${esc(it.id)}" title="Remove"><span class="ms">delete</span></md-icon-button>
    </div></div>`;
}
function stepsTab() {
  const f = W.edit;
  return f.steps.map((s, k) => `<div class="card" style="margin-bottom:16px" data-step="${esc(s.id)}">
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;margin-bottom:12px"><h2>Step ${k + 1}</h2><span class="muted small">${esc((f.screens.find(x => x.id === s.screen) || {}).name || '')} · ${esc(routeOfScreen(s.screen) || '')}</span></div>
    <div class="stepcard"><div>${shotBox(s)}</div>
      <div class="stack" style="gap:12px">
        <md-outlined-text-field data-step-field="action" type="textarea" rows="2" label="What the person does" value="${esc(s.action)}"></md-outlined-text-field>
        <md-outlined-text-field data-step-field="defaults" label="Defaults the task needs changed" value="${esc(s.defaults)}"></md-outlined-text-field>
        <label class="row small"><md-switch data-step-field="risky" ${s.risky ? 'selected' : ''}></md-switch>A mistake here is costly or hard to undo</label>
      </div></div>
    <h3 style="margin:20px 0 4px">What a person needs to know here</h3>
    <div>${f.items.filter(i => i.step === s.id).map(itemRow).join('') || '<p class="muted small">Nothing yet.</p>'}</div>
    <md-text-button data-act="add-item" data-step-id="${esc(s.id)}"><span slot="icon" class="ms">add</span>Add an item</md-text-button>
  </div>`).join('');
}
const LEVEL_WORDS = {true: ['Unknown','Everyday meaning','Knows it'], false: ['Unknown','Vaguely','Knows it']};
function knowledgeTab() {
  const f = W.edit, itemOf = id => f.items.find(i => i.id === id) || {id, text: id};
  return `<p class="muted" style="margin-top:0">Groups set knowledge for many items at once when a persona is made. Every item but a habit is in exactly one group; a word group holds only words.</p>
    ${f.knowledgeGroups.map((g, gi) => `<div class="card" style="margin-bottom:16px" data-group="${gi}">
      <div class="form" style="max-width:none"><div class="two"><md-outlined-text-field data-group-field="title" label="Title" value="${esc(g.title)}"></md-outlined-text-field>
        <md-outlined-text-field data-group-field="examples" label="Examples" value="${esc(g.examples)}"></md-outlined-text-field></div>
        <md-outlined-text-field data-group-field="description" label="Description" value="${esc(g.description)}"></md-outlined-text-field>
        <div class="row" style="flex-wrap:wrap"><span class="muted small">A typical user</span><div class="seg">${LEVEL_WORDS[!!g.word].map((l, v) => `<button type="button" class="${g.default === v ? 'on' : ''}" data-group-default="${gi}" data-v="${v}">${l}</button>`).join('')}</div>
          <span class="tag">${g.word ? 'Words' : 'Knowledge'}</span></div></div>
      <div class="chips" style="margin-top:12px">${g.items.map(id => { const it = itemOf(id); return `<span class="tag" title="${esc(it.meaning || '')}">${esc(id)} · ${esc(String(it.text).slice(0, 48))}
        <select data-move="${esc(id)}" aria-label="Move ${esc(id)}" style="border:0;background:transparent;color:inherit;font:inherit">${f.knowledgeGroups.map((o, oi) => (!!o.word === !!g.word) ? `<option value="${oi}" ${oi === gi ? 'selected' : ''}>${esc(o.title)}</option>` : '').join('')}</select></span>`; }).join('')}</div>
    </div>`).join('')}
    <div class="row"><md-text-button data-act="add-group" data-word="1"><span slot="icon" class="ms">add</span>Word group</md-text-button><md-text-button data-act="add-group" data-word="0"><span slot="icon" class="ms">add</span>Knowledge group</md-text-button></div>`;
}
function questionnaireTab() {
  const f = W.edit;
  const srcs = (f.sources || []).map(s => [s.id, (s.label || {}).en || s.id]);
  return `<div class="row" style="justify-content:space-between;flex-wrap:wrap;margin-bottom:12px"><p class="muted" style="margin:0">Real participants answer these before a test. Their answers decide what their persona card knows.</p>
      ${W.d.current ? '<md-text-button href="/questionnaire" target="_blank"><span slot="icon" class="ms">open_in_new</span>Open the questionnaire</md-text-button>' : ''}</div>
    <div class="card" style="margin-bottom:16px"><h3>Groups of experience</h3>
      ${f.groups.map((g, gi) => `<div class="kv" style="grid-template-columns:160px 1fr 1fr;margin-top:12px" data-egroup="${gi}">
        <md-outlined-select data-eg-field="source" label="Source">${srcs.map(([k, l]) => `<md-select-option value="${k}" ${g.source === k ? 'selected' : ''}><div slot="headline">${esc(l)}</div></md-select-option>`).join('')}</md-outlined-select>
        <md-outlined-text-field data-eg-field="en" label="Label" value="${esc(g.label.en)}"></md-outlined-text-field>
        <md-outlined-text-field data-eg-field="zh" label="中文" value="${esc(g.label.zh)}"></md-outlined-text-field></div>`).join('')}</div>
    ${f.experiences.map((e, ei) => `<div class="card" style="margin-bottom:12px" data-exp="${ei}">
      <div class="row" style="justify-content:space-between"><span class="idtag">${esc(e.id)}</span><md-icon-button data-act="del-exp" data-exp-i="${ei}" title="Remove"><span class="ms">delete</span></md-icon-button></div>
      <div class="form" style="max-width:none"><md-outlined-text-field data-exp-field="text" label="The experience" value="${esc(e.text)}"></md-outlined-text-field>
        <div class="two"><md-outlined-text-field data-exp-field="en" label="Question" value="${esc(e.question.en)}"></md-outlined-text-field>
          <md-outlined-text-field data-exp-field="zh" label="问题" value="${esc(e.question.zh)}"></md-outlined-text-field></div></div>
      <details class="more" style="margin-top:8px"><summary><span class="small">Teaches ${f.items.filter(i => (i.exps || []).includes(e.id)).length} items</span><span class="ms">expand_more</span></summary>
        <div class="chips" style="margin-top:8px">${f.items.map(i => `<md-filter-chip label="${esc(i.id)} ${esc(String(i.text).slice(0, 36))}" data-teach="${esc(e.id)}" data-teach-item="${esc(i.id)}" ${(i.exps || []).includes(e.id) ? 'selected' : ''}></md-filter-chip>`).join('')}</div></details>
    </div>`).join('')}
    <md-text-button data-act="add-exp"><span slot="icon" class="ms">add</span>Add an experience</md-text-button>`;
}
const kvText = o => Object.entries(o || {}).map(([k, v]) => `${k} = ${typeof v === 'string' ? v : JSON.stringify(v)}`).join('\n');
function kvParse(t) {
  const out = {};
  for (const line of String(t || '').split('\n')) {
    const m = line.match(/^\s*([^=]+?)\s*=\s*(.*?)\s*$/); if (!m) continue;
    let v = m[2]; if (/^[\[{]/.test(v) || /^(true|false|null|-?\d+(\.\d+)?)$/.test(v)) { try { v = JSON.parse(v); } catch (e) { /* keep text */ } }
    out[m[1]] = v;
  }
  return out;
}
function successTab() {
  const f = W.edit, e = f.engine, t = e.target || {kind: 'uat'};
  const saved = (W.d.recording || {}).saved || [];
  const checks = t.success || [];
  const routes = (e.routes || {}).path || [];
  return `<div class="card" style="margin-bottom:16px"><h3>What counts as done</h3><p class="muted small" style="margin:4px 0 12px">In plain words, as a report shows them.</p>
      ${(f.checks || []).map((c, i) => `<div class="kv" style="grid-template-columns:1fr auto;margin-top:8px"><md-outlined-text-field data-plain="${i}" value="${esc(c)}" aria-label="Criterion ${i + 1}"></md-outlined-text-field>
        <md-icon-button data-act="del-plain" data-i="${i}"><span class="ms">delete</span></md-icon-button></div>`).join('')}
      <md-text-button data-act="add-plain"><span slot="icon" class="ms">add</span>Add</md-text-button></div>
    ${t.kind === 'web' ? `<div class="card" style="margin-bottom:16px"><h3>How the engine grades a run</h3><p class="muted small" style="margin:4px 0 12px">Each check runs after the run, in the same signed-in browser. Prefer reading what was saved over looking for words on a page.</p>
      ${checks.map((c, i) => `<div class="card tonal" style="margin-top:12px;padding:16px" data-check="${i}">
        <div class="kv" style="grid-template-columns:1fr 200px auto"><md-outlined-text-field data-ck="name" label="Name" value="${esc(c.name)}"></md-outlined-text-field>
          <md-outlined-select data-ck="type" label="Check">${[['json','What was saved (JSON)'],['text','Words on a page'],['url','Where it ended']].map(([k, l]) => `<md-select-option value="${k}" ${c.type === k ? 'selected' : ''}><div slot="headline">${l}</div></md-select-option>`).join('')}</md-outlined-select>
          <md-icon-button data-act="del-check" data-i="${i}"><span class="ms">delete</span></md-icon-button></div>
        ${c.type === 'json' ? `<div class="form" style="max-width:none;margin-top:12px"><div class="two"><md-outlined-text-field data-ck="url" label="Read from (GET)" value="${esc(c.url)}"></md-outlined-text-field>
            <md-outlined-text-field data-ck="list" label="The list in the answer (optional)" value="${esc(c.list)}"></md-outlined-text-field></div>
          <div class="two"><md-outlined-text-field data-ck="where" type="textarea" rows="3" label="The new row is the one where" value="${esc(kvText(c.where))}" supporting-text="field = value, one per line"></md-outlined-text-field>
            <md-outlined-text-field data-ck="expect" type="textarea" rows="3" label="It must have" value="${esc(kvText(c.expect))}" supporting-text='A list is written as JSON: projects = ["Lyra"]'></md-outlined-text-field></div></div>`
        : c.type === 'text' ? `<div class="two" style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:16px"><md-outlined-text-field data-ck="url" label="Page to open" value="${esc(c.url)}"></md-outlined-text-field>
            <md-outlined-text-field data-ck="contains" label="Must show" value="${esc(c.contains)}"></md-outlined-text-field></div>`
        : `<md-outlined-text-field data-ck="matches" label="The final address matches (regular expression)" value="${esc(c.matches)}" style="width:100%;margin-top:12px"></md-outlined-text-field>`}
      </div>`).join('')}
      <md-text-button data-act="add-check"><span slot="icon" class="ms">add</span>Add a check</md-text-button>
      ${saved.length ? `<details class="more" style="margin-top:12px"><summary><span class="small">What the product saved while you recorded</span><span class="ms">expand_more</span></summary>
        ${saved.map(r => `<pre class="mono">${esc(r.method)} ${esc(r.path)}\n${esc(JSON.stringify(r.sent, null, 2))}</pre>`).join('')}</details>` : ''}
    </div>` : '<div class="card" style="margin-bottom:16px"><h3>Grading</h3><p class="muted small">Our platform grades what was saved itself.</p></div>'}
    <div class="card"><h3>How the product confirms it</h3>
      <div class="form" style="max-width:none;margin-top:12px">
        <div class="two"><md-outlined-text-field data-eng="created" label="What the task makes (as a list shows it)" value="${esc(e.created)}"></md-outlined-text-field>
          <md-outlined-select data-eng="list" label="The page that lists it"><md-select-option value="" ${!(e.routes.list || [])[0] ? 'selected' : ''}><div slot="headline">None</div></md-select-option>${routes.map(r => `<md-select-option value="${esc(r)}" ${(e.routes.list || [])[0] === r ? 'selected' : ''}><div slot="headline">${esc(r)}</div></md-select-option>`).join('')}</md-outlined-select></div>
        <div class="chips">${[['toast','A success message'],['list','It shows in a list'],['external','An email or notification'],['test','It can be tried out']].map(([k, l]) => `<md-filter-chip label="${l}" data-signal="${k}" ${(f.signals || {})[k] ? 'selected' : ''}></md-filter-chip>`).join('')}</div>
      </div></div>`;
}
function productTab() {
  const f = W.edit, e = f.engine;
  const list = (k, v) => `<md-outlined-text-field data-list="${k}" label="${esc(v)}" value="${esc((k.split('.').reduce((o, p) => (o || {})[p], e) || []).join(', '))}" supporting-text="Separate with commas"></md-outlined-text-field>`;
  return `<div class="card" style="margin-bottom:16px"><h3>Buttons</h3><div class="form" style="max-width:none;margin-top:12px">
      ${list('labels.consequential', 'Buttons that commit or cancel something (clicked only when sure)')}${list('labels.advancing', 'Buttons that only move on')}</div></div>
    <div class="card" style="margin-bottom:16px"><h3>Words</h3><div class="form" style="max-width:none;margin-top:12px">
      ${list('words.dataTerms', 'Data shown as it is to everyone (names, emails, ids)')}${list('words.forceFake', 'Jargon nobody outside knows, even if it looks English')}</div></div>
    <div class="card" style="margin-bottom:16px"><h3>Special items</h3><div class="form" style="max-width:none;margin-top:12px">
      ${list('items.entry', 'Items that say where the task starts')}${list('items.help', 'Help icons a person may know')}${list('items.review', 'Links that open what was just made')}</div></div>
    <div class="card"><h3>The person</h3><div class="form" style="max-width:none;margin-top:12px">
      <md-outlined-text-field data-top="org" label="Who they are in the product, and what they may do" value="${esc(f.org)}"></md-outlined-text-field>
      <div class="two"><md-outlined-select data-sit="urgency" label="Urgency">${['calm','urgent'].map(k => `<md-select-option value="${k}" ${(f.situation || {}).urgency === k ? 'selected' : ''}><div slot="headline">${k}</div></md-select-option>`).join('')}</md-outlined-select>
        <md-outlined-select data-sit="stakes" label="Stakes">${['low','high'].map(k => `<md-select-option value="${k}" ${(f.situation || {}).stakes === k ? 'selected' : ''}><div slot="headline">${k}</div></md-select-option>`).join('')}</md-outlined-select></div></div></div>`;
}
function nextItemId() { const n = Math.max(0, ...W.edit.items.map(i => Number(String(i.id).replace(/\D/g, '')) || 0)) + 1; return 'T' + String(n).padStart(2, '0'); }
function groupFor(kind) {
  const word = kind === 'word';
  let g = W.edit.knowledgeGroups.find(x => !!x.word === word);
  if (!g) { g = {key: word ? 'other-terms' : 'other-knowledge', title: word ? 'Other terms' : 'Other knowledge', word, default: 1, description: 'Added in review', examples: '', items: []}; W.edit.knowledgeGroups.push(g); }
  return g;
}
function regroup(it) {
  for (const g of W.edit.knowledgeGroups) g.items = g.items.filter(x => x !== it.id);
  if (it.kind !== 'habit') groupFor(it.kind).items.push(it.id);
  W.edit.knowledgeGroups = W.edit.knowledgeGroups.filter(g => g.items.length);
}
function rerenderTab() { const b = $('#wf-body'); if (b) b.innerHTML = reviewTab(W.tab); }


/* ---- tests: four steps (approved prototype-new-test.html), each asking only what only the researcher knows ---- */
pages.tests = async () => {
  await loadWorkflows();
  return `<div class="page">
    <div class="page-head"><div><h1>Tests</h1><p class="muted">One task on one product. Do it once; the engine works out the rest.</p></div>
      <md-filled-button data-go="new-test"><span slot="icon" class="ms">add</span>New test</md-filled-button></div>
    <div class="grid">${S.workflows.map(w => `<div class="card wcard" data-go="test/${w.id}">
      <div class="row" style="justify-content:space-between;align-items:flex-start"><h3>${esc(w.name)}</h3>${statusChip(w.status)}</div>
      <p class="muted small" style="margin:0">${esc(String(w.task || '').replace(/\+?\{run\}/g, '').split(/(?<=[.!?])\s/)[0])}</p>
      <div class="chips">${{change: '<span class="tag blue"><span class="ms">edit_note</span>Changes something</span>', answer: '<span class="tag green"><span class="ms">search</span>Finds an answer</span>', place: '<span class="tag"><span class="ms">location_on</span>Reaches a page</span>'}[w.outcome || 'change']}</div>
      <div class="meta"><span>${w.steps} step${w.steps === 1 ? '' : 's'}</span><span>${w.kind === 'web' ? esc((w.start || '').replace(/^https?:\/\//, '').split('/')[0]) : 'Our test platform'}</span>${w.current ? '<span style="color:var(--md-sys-color-primary)">Being tested</span>' : ''}</div>
    </div>`).join('')}
    <button class="card tonal wcard" data-go="new-test" style="display:grid;place-items:center;min-height:150px;border:0;font:inherit;color:inherit">
      <span style="text-align:center"><span class="ms" style="font-size:36px;color:var(--md-sys-color-primary)">add_circle</span><h3 style="margin-top:8px">New test</h3></span></button>
    </div></div>`;
};
function signInChoice(b = {}) {
  const login = b.login || {}, mode = login.mode === 'session' ? 'hand' : login.url ? 'form' : 'none';
  return `<div class="card tonal" style="padding:16px">
    <h3>Signing in</h3>
    <div class="seg" style="margin:10px 0" role="radiogroup" aria-label="Signing in">
      ${[['none', 'No sign-in'], ['form', 'Account and password'], ['hand', 'I sign in myself']].map(([k, l]) => `<button type="button" data-signin="${k}" class="${mode === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    <p class="muted small" id="signin-note" style="margin:0 0 8px">${mode === 'hand' ? 'For single sign-on or a second step: you sign in once in the recording window and the runs reuse it.' : mode === 'form' ? 'The engine signs in with this test account before every run.' : 'The product opens without signing in.'}</p>
    <div id="signin-form" class="form" ${mode === 'form' ? '' : 'hidden'}>
      <md-outlined-text-field id="b-login-url" label="Sign-in page" value="${esc(login.url || '/login')}"></md-outlined-text-field>
      <div class="two"><md-outlined-text-field id="b-login-user" label="Test account" ${login.user ? 'placeholder="Kept in engine/.env"' : ''}></md-outlined-text-field>
        <md-outlined-text-field id="b-login-pass" label="Password" type="password" ${login.user ? 'placeholder="Kept in engine/.env"' : ''}></md-outlined-text-field></div>
      <p class="hint">Kept only in engine/.env on this computer.</p></div></div>`;
}
function testForm(b = {}) {
  return `<div class="form">
    <md-outlined-text-field id="b-start" label="Product address" value="${esc(b.start)}" supporting-text="A test environment, never the live product: the test really clicks Send and Save."></md-outlined-text-field>
    <md-outlined-text-field id="b-task" type="textarea" rows="4" label="The task, as participants will read it" value="${esc(b.task)}"></md-outlined-text-field>
    <div class="two"><md-outlined-text-field id="b-name" label="A short name for this test" value="${esc(b.name)}"></md-outlined-text-field>
      <md-outlined-text-field id="b-product" label="Product (optional)" value="${esc(b.product)}"></md-outlined-text-field></div>
    ${signInChoice(b)}
    <details class="more"><summary><h3>Start clean every time (optional)</h3><span class="ms">expand_more</span></summary>
      <md-outlined-text-field id="b-reset" label="Reset address" value="${esc(b.reset)}" style="margin-top:12px;width:100%" supporting-text="A path the engine sends POST to before each run, e.g. /api/reset. Without one, you can record a clean-up after the task."></md-outlined-text-field>
    </details></div>`;
}
function readTestForm() {
  const v = id => ($(id) || {}).value || '';
  const mode = ($('[data-signin].on') || {dataset: {signin: 'none'}}).dataset.signin;
  const task = v('#b-task').trim();
  // A short name when none is given: the task's first words, without addresses and brackets.
  const short = task.replace(/\([^)]*\)|\S+@\S+/g, ' ').split(/(?<=[.!?])\s/)[0].split(/\s+/).filter(Boolean).slice(0, 7).join(' ').replace(/[.,;:]+$/, '');
  const out = {name: v('#b-name').trim() || short, product: v('#b-product'), start: v('#b-start'), task, reset: v('#b-reset')};
  if (mode === 'hand') out.login = {mode: 'session'};
  if (mode === 'form') out.login = {url: v('#b-login-url'), user: v('#b-login-user'), password: v('#b-login-pass')};
  return out;
}
pages['new-test'] = async () => `<div class="page" style="max-width:960px">
  <a class="backlink" href="#tests"><span class="ms">arrow_back</span>Tests</a>
  <div class="page-head"><div><h1>New test</h1><p class="muted">Four steps. You only tell us what only you know; we work out the rest.</p></div></div>
  ${vstep(1, 'What to test', 'open', '', `${testForm()}<div class="actions" style="justify-content:flex-start;margin-top:20px"><md-filled-button id="create-test">Continue</md-filled-button></div>
    <div class="banner info" style="margin-top:24px"><span class="ms">upload_file</span><div>Already have this test as a workflow file (the format our Version A test uses)? <a href="#" data-act="test-import">Import the file</a> and skip to the checks.
      <input type="file" id="import-file" accept=".json,application/json" hidden></div></div>`)}
  ${vstep(2, 'Do it once', '', '', '')}${vstep(3, 'What must be right at the end', '', '', '')}${vstep(4, 'We get it ready', '', '', '')}
</div>`;
/* One step of a test. A finished step's title takes you back into it (reopen), as in a stepper:
   it opens as it was set up, and the steps after it fold until it is saved again. */
function vstep(n, title, state, sum, body, reopen = false) {
  const num = state === 'done' || state === 'openDone' ? '<span class="ms" style="font-size:18px">check</span>' : n;
  const head = reopen ? `<button type="button" class="head reopen" data-test-edit="${n}" title="Go back to this step"><h2>${title}</h2><span class="ms">edit</span></button>`
    : `<div class="head"><h2>${title}</h2></div>`;
  return `<section class="vstep ${state === 'open' ? 'open' : ''} ${state === 'done' ? 'done' : ''} ${state === 'openDone' ? 'open done' : ''}" id="s${n}">
    <div class="rail-line"><span class="num">${num}</span><span class="line"></span></div>
    <div>${head}<p class="sum">${sum}</p><div class="body">${body}</div></div></section>`;
}
const stepActions = (save, label = 'Save') => `<div class="actions" style="justify-content:flex-start;margin-top:20px">${save}<md-text-button data-test-edit="0">Cancel</md-text-button></div>`;
const T = {id: null, d: null, facts: null, summary: null, poll: null, edit: 0};
pages.test = async (id) => {
  if (T.id !== id) T.edit = 0;
  T.id = id; clearTimeout(T.poll);
  const d = T.d = await api(`/api/workflow?id=${encodeURIComponent(id)}`);
  if (d.legacy) return legacyTest(d);
  const job = d.job ? await api(`/api/wjob?id=${d.job}`) : null;
  const rec = d.recording, hasRec = rec && rec.actions.length, st = d.status.key;
  const recording = job && job.kind === 'record', drafting = job && job.kind === 'draft', checking = job && job.kind === 'check';
  const host = (d.basics.start || '').replace(/^https?:\/\//, '').split('/')[0];
  const signIn = (d.basics.login || {}).mode === 'session' ? ' · you sign in yourself' : (d.basics.login || {}).url ? ' · signed in as a test account' : '';
  // 1
  const folded = n => T.edit && n > T.edit;  // a step after the one being changed
  let html = vstep(1, 'What to test', T.edit === 1 ? 'open' : 'done', `${esc(host)}${signIn} · “${esc(String(d.basics.task || '').split(/(?<=[.!?])\s/)[0])}”`,
    T.edit === 1 ? `${testForm(d.basics)}${stepActions('<md-filled-button id="save-test">Save</md-filled-button>')}` : '', T.edit !== 1 && !job);
  // 2
  const imported = !hasRec && !!d.flow && !recording;  // a workflow file: its steps came with it
  const s2open = (!hasRec && !imported) || recording || T.edit === 2;
  const caps = (rec || {}).capabilities || {};
  let body2 = '';
  if (recording && job.view.name === 'recording') {
    body2 = `${job.view.waitingForSignIn ? `<div class="banner info"><span class="ms">login</span><div>Sign in in the browser window that opened. When you see the product, press <b>I'm signed in</b>.<div style="margin-top:8px"><md-filled-tonal-button data-act="signed-in">I'm signed in</md-filled-tonal-button></div></div></div>` : ''}
      <div class="row small" style="gap:8px"><span class="rec-dot"></span><b>Recording</b><span class="muted">Do the task in the browser window</span></div>
      <div class="rec-list" id="rec-live">${(job.view.actions || []).map(actionLine).join('') || '<div class="muted">Waiting for the first step…</div>'}</div>
      <div class="actions" style="justify-content:flex-start;margin-top:12px"><md-filled-button data-act="stop-test-job">I'm done</md-filled-button></div>`;
  } else {
    body2 = `<p class="lead">A browser window opens on your product${signIn ? (d.basics.login.mode === 'session' ? '; sign in there first' : ', already signed in') : ''}. Do the task the way it <b>should</b> be done, as a person who knows the product would. We write down each step; we never record passwords.</p>
      <md-filled-button data-act="test-record"><span slot="icon" class="ms">open_in_new</span>${hasRec ? 'Record again' : 'Open the browser'}</md-filled-button>
      ${hasRec || imported ? '<md-text-button data-test-edit="0">Cancel</md-text-button>' : ''}
      <details class="more" style="margin-top:20px" ${d.basics.written ? 'open' : ''}><summary><h3>Or write the steps, and AI does them once</h3><span class="ms">expand_more</span></summary>
        <p class="muted small" style="margin:8px 0">One step per line, as you would tell a colleague. A browser window opens and AI carries out each line on your product while you watch; we write it down exactly as when you do it yourself.</p>
        <md-outlined-text-field id="w-steps" type="textarea" rows="6" style="width:100%" label="The right way, step by step" placeholder="Open Members from the left menu&#10;Click Invite people&#10;Enter the email address and set the role to Viewer&#10;Send the invite"></md-outlined-text-field>
        <div class="actions" style="justify-content:flex-start;margin-top:12px"><md-filled-tonal-button data-act="test-written"><span slot="icon" class="ms">auto_awesome</span>Let AI do it once</md-filled-tonal-button></div></details>`;
  }
  const extras = hasRec && !s2open && !d.basics.reset ? `<div class="sum" style="margin-top:6px">
      ${['setup', 'cleanup'].map(k => `<md-text-button data-act="test-record-${k}"><span slot="icon" class="ms">${rec[k] ? 'check_circle' : 'add'}</span>${k === 'setup' ? (rec[k] ? 'Set-up recorded' : 'Record what to set up before each run') : (rec[k] ? 'Clean-up recorded' : 'Record how to clean up after each run')}</md-text-button>`).join('')}</div>` : '';
  const extrasRunning = recording && job.view.name !== 'recording' ? `<div class="banner info" style="margin-top:8px"><span class="ms">radio_button_checked</span><div>Recording the ${job.view.name === 'setup' ? 'set-up' : 'clean-up'} in the browser window. ${(job.view.actions || []).length} steps so far. <a href="#" data-act="stop-test-job">I'm done</a></div></div>` : '';
  html += vstep(2, 'Do it once', s2open && !folded(2) ? 'open' : hasRec || imported ? 'done' : '', hasRec ? `${rec.actions.length} steps on ${new Set(rec.states.map(s => s.route)).size} pages` : imported ? `${d.flow.steps.length} steps, from your workflow file` : '',
    folded(2) ? '' : body2, (hasRec || imported) && !s2open && !job).replace('</p><div class="body">', `</p>${folded(2) ? '' : extras + extrasRunning}<div class="body">`);
  // 3
  const confirmed = !!d.check || checking;
  let state3 = (!hasRec && !imported) || s2open ? '' : imported ? 'done' : (drafting || !d.flow) ? 'open' : (!confirmed || T.edit === 3) ? 'open' : 'done';
  if (folded(3) && d.flow && confirmed) state3 = 'done';
  let body3 = '';
  if (state3 === 'open') {
    if (drafting || !d.flow) body3 = `<div class="drafting card tonal" style="max-width:none;margin:0"><div class="row"><md-circular-progress indeterminate style="--md-circular-progress-size:28px"></md-circular-progress><span>Reading what you did and what your product saved…</span></div>
      <div class="shimmer" style="width:90%;margin-top:20px"></div><div class="shimmer" style="width:70%"></div></div>`;
    else {
      T.facts = await api(`/api/facts?id=${encodeURIComponent(id)}`);
      body3 = factsHTML(T.facts);
    }
  }
  const nOn = T.facts ? T.facts.facts.filter(f => f.on).length : 0;
  html += vstep(3, 'What must be right at the end', state3, state3 === 'done' ? (n => `${n} check${n === 1 ? '' : 's'}, read from what your product saved`)((d.flow.engine.target.success || []).length) : '',
    state3 === 'open' && T.edit === 3 ? body3.replace(/<md-filled-button data-act="save-facts">Continue<\/md-filled-button><\/div>$/, '<md-filled-button data-act="save-facts">Continue</md-filled-button><md-text-button data-test-edit="0">Cancel</md-text-button></div>') : body3,
    state3 === 'done' && !job && !imported);
  // 4
  let state4 = '', body4 = '';
  if (folded(4)) state4 = st === 'ready' ? 'done' : '';
  else if (state3 === 'done') {
    state4 = st === 'ready' ? 'openDone' : 'open';
    if (checking) body4 = prepHTML(job.view.lines || [], true);
    else if (st === 'ready') { T.summary = await api(`/api/summary?id=${encodeURIComponent(id)}`); body4 = readyHTML(d, T.summary); }
    else body4 = failedHTML(d);
  }
  html += vstep(4, 'We get it ready', state4, st === 'ready' ? 'Ready' : '', body4);
  if (job && job.state === 'running') T.poll = setTimeout(() => pollTest(job.id), 1200);
  return `<div class="page" style="max-width:960px">
    <a class="backlink" href="#tests"><span class="ms">arrow_back</span>Tests</a>
    <div class="page-head"><div><div class="row" style="flex-wrap:wrap"><h1>${esc(d.name)}</h1>${statusChip(d.status)}</div></div>
    </div>
    ${html}</div>`;
};
/* The part of a screenshot around where a step happens, zoomed so its words can be read, with a
   ring on the control. Clicking it opens the whole screen. */
function shotCrop(url, size, box, alt, cw = 720) {
  if (!url) return '';
  if (!size || !box) return `<img src="${url}" alt="${esc(alt)}" loading="lazy" data-full="${url}">`;
  const [W, H] = size; cw = Math.min(cw, W); const ch = Math.min(H, Math.round(cw * 10 / 16));
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  const x0 = Math.max(0, Math.min(W - cw, cx - cw / 2)), y0 = Math.max(0, Math.min(H - ch, cy - ch / 2));
  const px = W > cw ? x0 / (W - cw) * 100 : 0, py = H > ch ? y0 / (H - ch) * 100 : 0;
  const ring = cx <= W && cy <= H ? `<span class="ring" style="left:${(cx - x0) / cw * 100}%;top:${(cy - y0) / ch * 100}%"></span>` : '';
  return `<button type="button" class="crop" data-full="${url}" title="See the whole screen" aria-label="${esc(alt)}; see the whole screen"
    style="aspect-ratio:${cw}/${ch};background-image:url('${url}');background-size:${W / cw * 100}% auto;background-position:${px}% ${py}%">${ring}</button>`;
}
function openFull(url) {
  let v = $('#viewer');
  if (!v) { v = document.createElement('div'); v.id = 'viewer'; v.className = 'viewer'; v.innerHTML = '<img alt="The whole screen"><md-icon-button aria-label="Close"><span class="ms">close</span></md-icon-button>'; document.body.appendChild(v);
    v.addEventListener('click', () => v.classList.remove('show')); }
  v.querySelector('img').src = url; v.classList.add('show');
}
document.addEventListener('click', e => { const f = e.target.closest('[data-full]'); if (f) { e.preventDefault(); openFull(f.dataset.full); } });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#viewer')) $('#viewer').classList.remove('show'); });

/* A test defined before the four steps (Version A, on our own platform): the same page and the same
   stepper. It was not recorded, so step 2 shows the steps the research team set, each on the screen
   where it happens (from the latest full-card run). Our platform grades the result itself, so
   step 3 chooses which of its checks count towards "done right"; it does not rewrite them. */
async function legacyTest(d) {
  T.summary = await api(`/api/summary?id=${encodeURIComponent(d.id)}`);
  const f = d.flow, e = f.engine || {}, labels = e.grading || {}, off = new Set(e.gradingIgnored || []);
  const keys = Object.keys(labels), counted = keys.filter(k => !off.has(k));
  const open = n => T.edit === n, folded = n => T.edit && n > T.edit;
  const s1 = open(1) ? `<md-outlined-text-field id="l-task" type="textarea" rows="6" label="The task, as participants read it" value="${esc(f.task)}" style="width:100%"></md-outlined-text-field>
      ${stepActions('<md-filled-button data-act="test-save-task">Save</md-filled-button>')}` : '';
  const s2 = open(2) ? `<p class="lead">The way a person who knows the product does it, one step per row. Change what a step says or what is easy to get wrong there.</p>
      <div class="story edit">${T.summary.steps.map((s, i) => `<div class="srow${s.shot ? '' : ' noshot'}"><span class="n">${i + 1}</span>${shotCrop(s.shot, s.shotSize, s.shotBox, `The screen for step ${i + 1}`)}
        <div style="display:grid;gap:8px;min-width:0">
          <md-outlined-text-field data-step-action="${esc(s.id)}" label="What to do" value="${esc(s.action)}" style="width:100%"></md-outlined-text-field>
          <md-outlined-text-field data-step-hard="${esc(s.id)}" label="Easy to get wrong (optional)" value="${esc(s.hard)}" style="width:100%"></md-outlined-text-field></div></div>`).join('')}</div>
      ${stepActions('<md-filled-button data-act="test-save-steps">Save</md-filled-button>')}` : '';
  const s3 = open(3) ? `<p class="lead">After every run our platform checks what was saved. Choose which checks count: a run is done right only when every check that counts is met. The others are still shown in the results.</p>
      <div class="card" id="checks">${keys.map(k => `<label class="fact" style="grid-template-columns:auto 1fr"><md-checkbox data-count="${esc(k)}" ${off.has(k) ? '' : 'checked'} touch-target="wrapper"></md-checkbox><span>${esc(labels[k])}</span></label>`).join('')}</div>
      ${stepActions('<md-filled-button data-act="test-save-checks">Save</md-filled-button>')}` : '';
  return `<div class="page" style="max-width:960px">
    <a class="backlink" href="#tests"><span class="ms">arrow_back</span>Tests</a>
    <div class="page-head"><div><div class="row" style="flex-wrap:wrap"><h1>${esc(d.name)}</h1>${statusChip(d.status)}</div></div></div>
    ${vstep(1, 'What to test', open(1) ? 'open' : 'done', `On our own test platform · “${esc(String(f.task || '').split(/(?<=[.!?])\s/)[0])}”`, s1, !open(1))}
    ${vstep(2, 'Do it once', open(2) ? 'open' : 'done', `${f.steps.length} steps, set by the research team with real participants`, folded(2) ? '' : s2, !open(2))}
    ${vstep(3, 'What must be right at the end', open(3) ? 'open' : 'done', `${counted.length} of ${keys.length} checks count: ${esc(counted.map(k => labels[k]).join('; '))}`, folded(3) ? '' : s3, !open(3))}
    ${vstep(4, 'We get it ready', T.edit ? 'done' : 'openDone', 'Ready', T.edit ? '' : readyHTML(d, T.summary, true))}
  </div>`;
}
function factsHTML(F) {
  const what = F.kind === 'answer' ? 'Your product shows the answer below. Check it is the right one.' : F.kind === 'place' ? 'The task ends on a page. Check how we recognise it.'
    : 'When you finished, your product saved the following. Tick what the task requires.';
  return `<p class="lead">${what} After every run we check these in what was saved, not by which page the person ends on: reaching the right page with the wrong settings is the mistake we most want to catch.</p>
    <div class="card" id="facts">${F.facts.map(f => `<div class="fact">
      ${f.fixed ? '<span class="ms" style="color:var(--md-sys-color-primary);justify-self:center">key</span>' : `<md-checkbox data-fact="${esc(f.key)}" ${f.on ? 'checked' : ''} touch-target="wrapper"></md-checkbox>`}
      <label>${esc(f.text)}</label>
      <div class="why"><span class="ms">auto_awesome</span>${esc(f.why || '')}</div>
      ${f.answer ? `<div style="grid-column:2"><md-outlined-text-field data-answer-key="${esc(f.key)}" label="Right answers, separated by commas" value="${esc(f.answer.join(', '))}" style="width:100%"></md-outlined-text-field></div>` : ''}
      ${f.unique || f.isUnique ? `<label class="row small" style="grid-column:2;gap:8px"><md-switch data-unique="${esc(f.key)}" ${f.isUnique ? 'selected disabled' : 'selected'}></md-switch>Different in every run, so runs never meet each other's data</label>` : ''}
    </div>`).join('')}</div>
    ${F.noReset ? '<p class="muted small">Your product has no reset address: runs leave what they saved. Make the identifying value different in every run, or record a clean-up in step 2.</p>' : ''}
    <div class="actions" style="justify-content:flex-start;margin-top:20px"><md-filled-button data-act="save-facts">Continue</md-filled-button></div>`;
}
function prepHTML(lines, running) {
  const WORK = [['flow file', 'Splitting what you did into steps and what a person needs to know'], ['full card', 'Checking that someone who knows everything can finish'],
    ['locator', 'Checking that every step finds its control on the page'], ['blank card', 'Checking that someone who knows nothing gets stuck']];
  return `<div class="card prep"><div class="checklist">${WORK.map(([k, w], i) => {
    const line = lines.find(l => l.toLowerCase().includes(k));
    const icon = line ? (/\[pass\]/.test(line) ? 'check_circle' : 'error') : running ? (i === 0 || lines.length >= i ? 'progress_activity' : 'radio_button_unchecked') : 'radio_button_unchecked';
    return `<div class="crow"><span class="ms ${icon === 'check_circle' ? 'ok' : icon === 'error' ? 'bad' : icon === 'progress_activity' ? 'spin' : ''}">${icon}</span><span>${w}</span><span></span></div>`; }).join('')}</div></div>`;
}
function notesHTML(d) {
  const caps = ((d.recording || {}).capabilities) || {};
  const items = [];
  if (caps.captcha) items.push(['block', 'Your product shows a CAPTCHA. The engine cannot pass it: turn it off in the test environment.']);
  if (caps.canvas) items.push(['draw', 'Part of your product is drawn on a canvas. The engine reads its text from the screen itself, which is less exact.']);
  if (caps.chinese) items.push(['translate', 'Your product is in Chinese. Personas read it with their own level of Chinese.']);
  for (const n of (d.notes || []).filter(n => !n.startsWith('Engine:'))) items.push(['info', n]);
  return items.length ? `<details class="more" style="margin-top:12px"><summary><span class="small">${items.length} thing${items.length > 1 ? 's' : ''} we noticed</span><span class="ms">expand_more</span></summary>
    ${items.map(([i, t]) => `<div class="row small" style="align-items:flex-start;margin-top:8px"><span class="ms" style="font-size:18px">${i}</span><span>${esc(t)}</span></div>`).join('')}</details>` : '';
}
function readyHTML(d, S2, legacy) {
  return `${legacy ? '' : prepHTML((d.check || {}).checks ? d.check.checks.map(c => `[${c.ok ? 'pass' : 'FAIL'}] ${c.name}`) : [], false)}
    <div class="card" style="${legacy ? '' : 'margin-top:16px'}">
      <div class="row" style="justify-content:space-between;flex-wrap:wrap"><div class="row"><span class="ms ok" style="font-size:28px">verified</span><div><h2>Ready to test</h2>
        <p class="muted small" style="margin:2px 0 0">${legacy ? 'Checked against real participants on our own platform.' : 'Someone who knows everything finished; someone who knows nothing got stuck.'}</p></div></div>
        <md-filled-button data-act="test-use"><span slot="icon" class="ms">play_arrow</span>Choose personas and run</md-filled-button></div>
      <h3 style="margin:24px 0 4px">The task, step by step</h3>
      <div class="story">${S2.steps.map((s, i) => `<div class="srow${s.shot ? '' : ' noshot'}"><span class="n">${i + 1}</span>${shotCrop(s.shot, s.shotSize, s.shotBox, `The screen for step ${i + 1}`)}<div>${esc(s.action)}
        ${s.hard ? `<div style="margin-top:6px"><span class="tag amber"><span class="ms">warning</span>Easy to get wrong: ${esc(s.hard)}</span></div>` : ''}</div></div>`).join('')}</div>
      <details class="more" style="margin-top:16px"><summary><h3>What a person needs to know</h3><span class="ms">expand_more</span></summary>
        <ul style="margin:8px 0 0;padding-left:20px;line-height:1.8">${S2.know.map(k => `<li>${esc(k.text)}${k.meaning && k.meaning !== k.text ? ` <span class="muted small">(${esc(k.meaning)})</span>` : ''}</li>`).join('')}</ul>
        ${S2.traps.length ? `<p class="small" style="margin:12px 0 4px"><b>Habits from other products that may mislead</b></p><ul style="margin:0;padding-left:20px">${S2.traps.map(t => `<li>${esc(t.text)}</li>`).join('')}</ul>` : ''}
        <p class="muted small">Each persona knows some of these and not others. What they don't know, they see as made-up words or covered icons.</p></details>
      ${legacy ? '' : notesHTML(d)}
      <div class="fix"><md-outlined-text-field id="fix" label="Something not right? Tell us in a sentence" placeholder="${legacy ? "e.g. Most people don't know Atlas is a project name" : "e.g. Most people don't know a Viewer can't comment"}"></md-outlined-text-field>
        <md-filled-tonal-button data-act="test-adjust">Update</md-filled-tonal-button></div>
    </div>`;
}
function failedHTML(d) {
  const c = d.check;
  if (!c) return `${prepHTML([], false)}<div class="actions" style="justify-content:flex-start;margin-top:12px"><md-filled-button data-act="test-check">Check it</md-filled-button></div>`;
  const stale = d.status.key === 'changed';
  return `${prepHTML(c.checks.map(x => `[${x.ok ? 'pass' : 'FAIL'}] ${x.name}`), false)}
    <div class="banner ${stale ? 'info' : 'bad'}" style="margin-top:16px"><span class="ms">${stale ? 'update' : 'error'}</span><div>
      ${stale ? 'You changed the test since it was checked.' : '<b>Not ready yet</b>'}
      <ul>${c.checks.filter(x => !x.ok && x.required).map(x => `<li>${esc(x.name)}: ${esc(x.detail)}${x.run ? ` · <a href="/runs/${esc(x.run.split(/[\\/]/).pop())}/report.html" target="_blank">see the run</a>` : ''}</li>`).join('')}</ul>
      <div class="row" style="margin-top:8px;flex-wrap:wrap"><md-filled-tonal-button data-act="test-check">Check again</md-filled-tonal-button><md-text-button data-act="test-record">Record again</md-text-button></div></div></div>${notesHTML(d)}`;
}
async function pollTest(jid) {
  clearTimeout(T.poll);
  if (!location.hash.startsWith('#test/')) return;
  try {
    const j = await api(`/api/wjob?id=${jid}`);
    if (j.state === 'running') {
      if (j.kind === 'record' && $('#rec-live')) $('#rec-live').innerHTML = (j.view.actions || []).map(actionLine).join('') || '<div class="muted">Waiting for the first step…</div>';
      if (j.kind === 'check' && $('#s4 .prep')) $('#s4 .body').innerHTML = prepHTML(j.view.lines || [], true);
      T.poll = setTimeout(() => pollTest(jid), 1200);
      return;
    }
    if (j.kind === 'record' && j.state !== 'failed') {
      if (j.view.name === 'recording' && j.view.stuck) { snack(j.view.stuck); T.edit = 2; }
      else if (j.view.name === 'recording') { if ((j.view.actions || []).length) { await api('/api/workflows/draft', {id: T.id}); T.edit = 0; } }
      else if (T.d.flow) { await api('/api/workflows/steps', {id: T.id, name: j.view.name}); snack(`${j.view.name === 'setup' ? 'Set-up' : 'Clean-up'} recorded. The test will be checked again.`); await api('/api/workflows/check', {id: T.id}); }
    } else if (j.kind === 'check' && j.state === 'completed') snack('Ready to test.');
    else if (j.state === 'failed' && j.kind !== 'check') snack(`That did not work: ${(j.log || '').trim().split('\n').slice(-1)[0].slice(0, 160)}`);
    render();
  } catch (e) { fail(e); }
}
async function testAct(name, t) {
  switch (name) {
    case 'test-record': if (T.d.recording && T.d.recording.actions.length && !(await confirmBox('Record the task again?', 'The new recording replaces this one, and the test is worked out again from it.', 'Record'))) return;
      await api('/api/workflows/record', {id: T.id}); T.edit = 2; snack('A browser window is opening. Do the task there.'); return render();
    case 'test-record-setup': case 'test-record-cleanup': {
      const which = name.endsWith('setup') ? 'setup' : 'cleanup';
      await api('/api/workflows/record', {id: T.id, name: which});
      snack(which === 'setup' ? 'Do what must exist before each run (for example, create the request to approve).' : 'Undo what the task did (for example, delete the invite).');
      return render();
    }
    case 'signed-in': await api('/api/workflows/signed-in', {id: T.id}); return snack('Thanks. Now do the task.');
    case 'stop-test-job': return api('/api/jobs/stop', {id: T.d.job});
    case 'save-facts': {
      const facts = T.facts.facts.map(f => {
        const box = document.querySelector(`[data-fact="${CSS.escape(f.key)}"]`), ans = document.querySelector(`[data-answer-key="${CSS.escape(f.key)}"]`);
        const uniq = document.querySelector(`[data-unique="${CSS.escape(f.key)}"]`);
        return {key: f.key, on: box ? box.checked : true, answer: ans ? ans.value.split(',').map(x => x.trim()).filter(Boolean) : undefined, unique: uniq ? uniq.selected : false};
      });
      await api('/api/workflows/facts', {id: T.id, facts});
      await api('/api/workflows/check', {id: T.id}); T.edit = 0; return render();
    }
    case 'test-check': await api('/api/workflows/check', {id: T.id}); return render();
    case 'test-written': {
      const text = ($('#w-steps').value || '').trim();
      if (!text) return snack('Write the steps first, one per line.');
      await api('/api/workflows/record', {id: T.id, written: text}); T.edit = 2;
      snack('A browser window is opening. AI is doing your steps there.'); return render();
    }
    case 'test-import': $('#import-file').click(); return;
    case 'test-use': await api('/api/workflows/select', {id: T.id}); location.hash = 'run'; return location.reload();
    case 'test-adjust': {
      const text = ($('#fix').value || '').trim(); if (!text) return;
      t.disabled = true;
      try { const r = await api('/api/workflows/adjust', {id: T.id, text});
        snack(`Updated: ${r.added.length} added, ${r.changed} changed, ${r.removed.length} removed.${T.d.legacy ? '' : ' Checking again.'}`);
        if (!T.d.legacy) await api('/api/workflows/check', {id: T.id});
        render(); } finally { t.disabled = false; }
      return;
    }
    case 'test-save-task': await api('/api/workflows/text', {id: T.id, task: $('#l-task').value}); T.edit = 0; snack('Saved.'); return render();
    case 'test-save-steps': {
      const steps = $$('[data-step-action]').map(f => ({id: f.dataset.stepAction, action: f.value,
        hard: document.querySelector(`[data-step-hard="${CSS.escape(f.dataset.stepAction)}"]`).value}));
      await api('/api/workflows/text', {id: T.id, steps}); T.edit = 0; snack('Saved.'); return render();
    }
    case 'test-save-checks': {
      const ignored = $$('[data-count]').filter(c => !c.checked).map(c => c.dataset.count);
      await api('/api/workflows/text', {id: T.id, ignored}); T.edit = 0; snack('Saved. Results count only the checks you kept.'); return render();
    }
  }
}

/* ---- personas ---- */
pages.personas = async () => {
  await loadPersonas();
  return `<div class="page">
    <div class="page-head"><div><h1>Personas</h1><p class="muted">Each persona is one kind of user of ${esc((currentWf() || {}).name || 'this workflow')}.</p></div>
      <md-filled-button data-go="new"><span slot="icon" class="ms">add</span>New persona</md-filled-button></div>
    <div class="grid">${S.personas.map(personaCard).join('')}${newCard()}</div>
  </div>`;
};
const SUGGEST = [['Careful first-time user', 'Someone using this product for the first time who reads carefully and checks every field before saving'],
  ['Experienced admin in a hurry', 'An experienced admin who knows the product well but is in a hurry and skims the defaults'],
  ['Tired at the end of the day', 'A tired user at the end of a long day who gets distracted and gives up quickly']];
let draft = null;
function groupsVisible() { return PersonaParameters.GROUPS.filter(g => !g.hidden); }
function sourceTag(src, key) {
  const u = (src || {})[key];
  return u ? `<span class="source" title="${esc(u.reason || '')}"><span class="ms">format_quote</span>“${esc(u.quote)}”${u.confidence === 'inferred' ? ' · our reading' : ''}</span>` : '';
}
function editorHTML(p, flat, src) {
  const box = flat ? 'sec' : 'card', hf = p.humanFactors || {};
  return `
    <div class="${box}"><h2>How they work</h2><p class="muted small" style="margin:6px 0 12px">Each run draws from these, so no two runs are quite the same.</p>
      ${TRAITS.map(t => `<div class="trait"><div class="head"><h3>${t.title}</h3></div>
        <md-slider min="0" max="10" step="0.5" value="${p[t.key]}" labeled data-trait="${t.key}" aria-label="${t.title}"></md-slider>
        <div class="readout" data-r="${t.key}">${esc(readout(t, p[t.key]))}</div>${sourceTag(src, t.key)}</div>`).join('')}</div>
    <div class="${box}"><h2>During the task</h2><p class="muted small" style="margin:6px 0 12px">Off unless you turn them up.</p>
      ${STATES.map(s => `<div class="trait"><div class="head"><h3>${s.title}</h3></div>
        <md-slider min="0" max="10" step="0.5" value="${p[s.key]}" labeled data-trait="${s.key}" aria-label="${s.title}"></md-slider>
        <div class="readout">${s.note}</div>${sourceTag(src, s.key)}</div>`).join('')}</div>
    <div class="${box}"><h2>What they know</h2><p class="muted small" style="margin:6px 0 12px">Terms they don't know show up as made-up words, as they would to them.</p>
      ${groupsVisible().map(g => `<div class="knowrow"><div style="min-width:0"><h3>${esc(g.title)}</h3><div class="muted small">${esc(g.examples || g.description)}</div></div>
        <div class="seg" role="radiogroup" aria-label="${esc(g.title)}">${LEVEL_WORDS[!!g.word].map((l, i) =>
          `<button type="button" role="radio" aria-checked="${p.knowledge[g.key] === i}" class="${p.knowledge[g.key] === i ? 'on' : ''}" data-know="${esc(g.key)}" data-v="${i}">${l}</button>`).join('')}</div></div>${sourceTag(src, 'knowledge.' + g.key)}`).join('')}</div>
    <details class="${box} more"><summary><h2>Seeing, clicking and warnings</h2><span class="ms">expand_more</span></summary>
      <md-list style="margin-top:8px;background:transparent">${PERCEPTION.map(([k, v, i, l]) =>
        `<md-list-item><span slot="start" class="ms">${i}</span><div slot="headline">${l}</div><md-switch slot="end" data-perc="${k}" data-on="${v}" ${hf[k] === v ? 'selected' : ''} aria-label="${l}"></md-switch></md-list-item>`).join('')}</md-list></details>
    <details class="${box} more"><summary><h2>Language and finishing</h2><span class="ms">expand_more</span></summary>
      <div class="knowrow" style="border-top:0"><div><h3>English</h3></div><div class="seg">${['beginner','intermediate','fluent'].map(k => `<button type="button" class="${p.english === k ? 'on' : ''}" data-english="${k}">${k[0].toUpperCase() + k.slice(1)}</button>`).join('')}</div></div>
      <h3 style="margin-top:12px">How they make sure it is done</h3>
      <div class="chips" style="margin-top:8px">${WAYS.map(([k, l]) => `<md-filter-chip label="${l}" data-way="${k}" ${p.confirmBy.includes(k) ? 'selected' : ''}></md-filter-chip>`).join('')}</div></details>`;
}
function scoresOf(p) { return Object.fromEntries([...TRAITS, ...STATES].map(t => [t.key, p[t.key]])); }
function knownOf(p) { const g = groupsVisible(); return g.length ? g.reduce((s, x) => s + p.knowledge[x.key], 0) / (2 * g.length) : 0; }
function buildBundle(p) {
  if (!S.builder) throw Error('The persona builder is still loading. Try again in a moment.');
  return PersonaParameters.build(PersonaParameters.validate(p), S.builder, S.flow);
}
function renderReview() {
  const p = draft.p, survey = draft.kind === 'survey';
  const kept = survey && draft.unknowns && draft.unknowns.length
    ? `<div class="banner" style="margin:0"><span class="ms">help</span><div><b>Their answers do not say</b>, so these stay at a typical level; adjust them if you know better:
       <div class="chips" style="margin-top:8px">${[...new Set(draft.unknowns.map(settingName))].map(u => `<span class="tag">${esc(u)}</span>`).join('')}</div></div></div>` : '';
  $('#draft-area').innerHTML = `<div class="review" style="margin-top:40px">
    <div class="stack" data-editor="draft">${survey ? `<div class="banner info" style="margin:0"><span class="ms">format_quote</span><div>Every setting below that changed comes with what they said. “Our reading” marks an interpretation rather than something they said outright.</div></div>${kept}` : ''}
      ${editorHTML(p, false, draft.src)}</div>
    <div class="card summary">
      <div class="row">${avatar({id: 'draft', name: p.name}, 56)}<div style="min-width:0;flex:1"><md-outlined-text-field id="p-name" label="${survey ? 'Code name' : 'Name'}" value="${survey ? '' : esc(p.name)}" ${survey ? 'placeholder="P4" supporting-text="Only a code name is kept, never their name."' : ''} style="width:100%"></md-outlined-text-field></div></div>
      <p style="margin:12px 0">${survey ? esc(draft.description) : `“${esc(draft.description)}”`}</p>
      <div class="chips" id="sum-chips">${chipsFor(scoresOf(p), knownOf(p), p.humanFactors)}</div>
      <md-filled-button id="create" style="width:100%;margin-top:12px"><span slot="icon" class="ms">check</span>Create persona</md-filled-button>
      <md-outlined-button id="create-run" style="width:100%;margin-top:8px"><span slot="icon" class="ms">play_arrow</span>Create and run a test</md-outlined-button>
    </div></div>`;
  $('#draft-area').scrollIntoView({behavior: 'smooth', block: 'start'});
}
pages.new = async () => `<div class="page">${composerHTML()}<div id="draft-area"></div></div>`;
function composerHTML(hello) {
  draft = null;
  return `<div class="composer">
    ${hello ? `<p class="muted" style="margin:0 0 4px;font-size:16px">${esc(hello)}</p>` : ''}
    <h1>Who do you want to <span class="spark">test with?</span></h1>
    <p class="muted" style="font-size:16px;margin-top:12px">Describe them like you would to a colleague, or paste a participant's survey answers. You can fine-tune everything afterwards.</p>
    <div class="prompt">
      <md-icon-button id="attach-btn" aria-label="Attach a participant's answers" title="Attach a participant's answers (.json, .txt, .md, .csv)" style="align-self:flex-end;margin-bottom:4px"><span class="ms">attach_file</span></md-icon-button>
      <input id="attach" type="file" accept=".json,.txt,.md,.csv" hidden>
      <textarea id="describe" rows="1" placeholder="e.g. An office manager who sets this up between meetings"></textarea>
      <md-filled-icon-button id="draft-btn" aria-label="Draft persona" disabled><span class="ms">arrow_upward</span></md-filled-icon-button>
    </div>
    <div class="chips">${SUGGEST.map(([l, t]) => `<md-suggestion-chip label="${esc(l)}" data-text="${esc(t)}"></md-suggestion-chip>`).join('')}</div>
    <p class="muted small" style="margin-top:14px">A participant filled in the survey? Paste their answers or attach the answer file: the persona is built from what they said.</p>
  </div>`;
}

/* What was pasted: a questionnaire answer file, other survey answers or an interview, or a description. */
function readInput(text) {
  try {
    const doc = JSON.parse(text);
    if (doc && doc.kind === 'sue-questionnaire' && doc.answers) return {kind: 'answers', doc};
    if (doc && typeof (doc.transcript || doc.text) === 'string') return {kind: 'survey', text: doc.transcript || doc.text};
  } catch (e) { /* not JSON */ }
  const lines = text.split(/\n/).filter(l => l.trim());
  const qa = lines.filter(l => /\?\s*$|^\s*(q\d*|a\d*|question|answer)\b|:\s*\S/i.test(l)).length;
  return text.length > 600 || (lines.length >= 4 && qa >= 3) ? {kind: 'survey', text} : {kind: 'description', text};
}
const LEVEL_SCORE = {low: 0, medium: 5, high: 10};
function codeOf(name) { return /^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(String(name || '').trim()) && String(name).trim().length <= 8 ? String(name).trim() : ''; }

function setupComposer() {
  const box = $('#describe'), btn = $('#draft-btn');
  const grow = () => { box.style.height = 'auto'; box.style.height = Math.min(box.scrollHeight, 200) + 'px'; box.style.overflowY = box.scrollHeight > 200 ? 'auto' : 'hidden'; btn.disabled = !box.value.trim(); };
  grow();
  box.addEventListener('input', grow);
  box.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && readInput(box.value).kind === 'description') { e.preventDefault(); if (box.value.trim()) start(); } });
  $$('md-suggestion-chip').forEach(c => c.addEventListener('click', () => { box.value = c.dataset.text; grow(); box.focus(); }));
  $('#attach-btn').addEventListener('click', () => $('#attach').click());
  $('#attach').addEventListener('change', async () => {
    const f = $('#attach').files[0]; if (!f) return;
    box.value = await f.text(); grow(); $('#attach').value = '';
    start();
  });
  btn.addEventListener('click', start);
  const wait = msg => `<div class="drafting card tonal"><div class="row"><md-circular-progress indeterminate style="--md-circular-progress-size:28px"></md-circular-progress><span>${msg}</span></div>
      <div class="shimmer" style="width:90%;margin-top:20px"></div><div class="shimmer" style="width:70%"></div><div class="shimmer" style="width:80%"></div></div>`;
  async function start() {
    const text = box.value.trim(); if (!text) return;
    const input = readInput(text);
    btn.disabled = true;
    try {
      if (input.kind === 'answers') return fromAnswers(input.doc);
      if (input.kind === 'survey') {
        $('#draft-area').innerHTML = wait('Reading their answers: every setting has to come from something they said…');
        const r = await api('/api/extract-interview', {text: input.text});
        const p = PersonaParameters.defaults(), src = {};
        for (const u of r.updates) {
          if (u.path.startsWith('knowledge.')) PersonaParameters.setGroup(p, u.path.slice(10), u.value);
          else if (u.path.startsWith('humanFactors.')) p.humanFactors[u.path.slice(13)] = u.value;
          else p[u.path] = u.value;
          src[u.path] = u;
        }
        p.name = 'Participant';
        draft = {kind: 'survey', p: PersonaParameters.validate(p), description: r.summary, src, unknowns: r.unknowns};
        return renderReview();
      }
      $('#draft-area').innerHTML = wait('Drafting a persona from your description…');
      const base = PersonaParameters.defaults(); base.name = 'New persona';
      const r = await api('/api/personas/draft', {prompt: PersonaParameters.prompt(text, base)});
      let p;
      try { p = PersonaParameters.fromJSON(JSON.stringify(r.settings.format ? r.settings : {format: 'sue-studio-settings', version: 3, parameters: r.settings})); }
      catch (e) { p = PersonaParameters.validate({...base, ...(r.settings.parameters || r.settings)}); }
      draft = {kind: 'description', p, description: text};
      renderReview();
    } catch (e) { $('#draft-area').innerHTML = `<div class="banner bad" style="margin-top:24px"><span class="ms">error</span><div>${esc(e.message)}</div></div>`; }
    finally { btn.disabled = false; }
  }
}

/* A participant's own questionnaire answers: the Persona Builder builds the card exactly, no AI. */
function fromAnswers(doc) {
  const here = (S.flow || {}).name || '';
  if (doc.flow && doc.flow !== here) {
    const other = S.workflows.find(w => w.name === doc.flow);
    $('#draft-area').innerHTML = `<div class="banner bad" style="margin-top:24px"><span class="ms">error</span><div>These answers were given for <b>${esc(doc.flow)}</b>, not for the test you are on (${esc(here)}).
      ${other ? `<div style="margin-top:8px"><md-filled-tonal-button data-flow="${esc(other.id)}">Switch to that test</md-filled-tonal-button></div>` : ''}</div></div>`;
    return;
  }
  if (!S.builder) throw Error('The persona builder is still loading. Try again in a moment.');
  S.builder.load(doc, 'normal');
  const card = S.builder.buildCard();
  draft = {kind: 'answers', doc, card};
  const t = card.tendency || {}, items = card.items.filter(i => i.kind !== 'habit');
  const knows = items.filter(i => i.result === 'understands').length, vague = items.filter(i => ['vague', 'everyday', 'other'].includes(i.result)).length;
  const groups = groupsVisible().map(g => {
    const mine = items.filter(i => g.ids.includes(i.id)), k = mine.filter(i => i.result === 'understands').length;
    return `<div class="knowrow"><div style="min-width:0"><h3>${esc(g.title)}</h3><div class="muted small">${esc(g.examples || g.description)}</div></div><span class="tag ${k === mine.length ? 'green' : k ? 'blue' : ''}">Knows ${k} of ${mine.length}</span></div>`;
  }).join('');
  const lang = (card.persona || {}).lang || {}, goal = card.goal || {};
  const scores = Object.fromEntries(TRAITS.map(x => [x.key, LEVEL_SCORE[(t[x.key] || {}).level] ?? 5]));
  $('#draft-area').innerHTML = `<div class="review" style="margin-top:40px">
    <div class="stack">
      <div class="banner info" style="margin:0"><span class="ms">fact_check</span><div>Built from their own answers, the same way as every participant's card: what they have done decides what they know. Nothing here is guessed by AI.</div></div>
      <div class="card"><h2>How they work</h2><p class="muted small" style="margin:6px 0 12px">From their answers about what they do when they are unsure.</p>
        ${TRAITS.map(x => `<div class="trait"><h3>${x.title}</h3><div class="readout">${esc(readout(x, scores[x.key]))}</div><div class="muted small">${esc((t[x.key] || {}).source || '')}</div></div>`).join('')}</div>
      <div class="card"><h2>What they know</h2><p class="muted small" style="margin:6px 0 12px">${knows} of ${items.length} things the task needs they understand; ${vague} they half know.</p>${groups}</div>
      <div class="card"><h2>Language and finishing</h2>
        <div class="knowrow" style="border-top:0"><h3>English</h3><span>${esc(lang.english || 'fluent')}${lang.vocabSize ? ` · about ${lang.vocabSize.toLocaleString()} words` : ''}</span></div>
        <div class="knowrow"><h3>How they make sure it is done</h3><span>${esc((goal.confirmBy || []).map(w => (WAYS.find(([k]) => k === w) || [w, w])[1]).join('; '))}</span></div></div>
    </div>
    <div class="card summary">
      <div class="row">${avatar({id: 'draft', name: codeOf(doc.answers.name) || 'P'}, 56)}<div style="min-width:0;flex:1">
        <md-outlined-text-field id="p-name" label="Code name" value="${esc(codeOf(doc.answers.name))}" placeholder="P4" style="width:100%" supporting-text="Only a code name is kept, never their name."></md-outlined-text-field></div></div>
      <div class="chips" style="margin-top:12px">${chipsFor({...scores, fatigue: 0, distraction: 0, timePressure: 0}, items.length ? knows / items.length : 0)}</div>
      <md-filled-button id="create" style="width:100%;margin-top:12px"><span slot="icon" class="ms">check</span>Create persona</md-filled-button>
      <md-outlined-button id="create-run" style="width:100%;margin-top:8px"><span slot="icon" class="ms">play_arrow</span>Create and run a test</md-outlined-button>
    </div></div>`;
  $('#draft-area').scrollIntoView({behavior: 'smooth', block: 'start'});
}

/* A questionnaire card as editor settings, item by item, so the editor starts exactly where their
   answers put them. The card itself stays as built; the server keeps whatever is not changed. */
function paramsFromCard(card, name) {
  const P = PersonaParameters, p = P.defaults();
  p.name = name;
  const score = {low: 0, medium: 5, high: 10}, t = card.tendency || {};
  for (const k of P.TRAITS) p[k] = typeof (t[k] || {}).score === 'number' ? t[k].score : score[(t[k] || {}).usual || (t[k] || {}).level] ?? 5;
  const g = card.goal || {}, lang = (card.persona || {}).lang || {};
  Object.assign(p, (g.situation && {urgency: g.situation.urgency || 'calm', stakes: g.situation.stakes || 'low'}) || {});
  p.english = ['fluent', 'intermediate', 'beginner'].includes(lang.english) ? lang.english : 'fluent';
  p.vocabSize = Number.isInteger(lang.vocabSize) ? lang.vocabSize : null;
  const ways = (g.confirmBy || []).filter(w => ['action', 'list', 'toast', 'external', 'test'].includes(w));
  p.confirmBy = ways.length ? [...new Set(ways)] : ['list'];
  if (['let_go', 'check', 'redo'].includes(g.ifConfirmMissing)) p.ifConfirmMissing = g.ifConfirmMissing;
  const per = card.perception || {}, lvl = x => (x || {}).level;
  p.humanFactors.vision = {high: 'normal', medium: 'mild', low: 'reduced'}[lvl(per.vision)] || 'normal';
  p.humanFactors.clickPrecision = {high: 'high', medium: 'medium', low: 'low'}[lvl(per.motor)] || 'high';
  p.humanFactors.readingSpeed = {high: 'fast', medium: 'average', low: 'slow'}[lvl(per.speed)] || 'average';
  p.humanFactors.colorVision = per.colorWeak ? 'reduced' : 'typical';
  const items = new Map(card.items.map(i => [i.id, i]));
  const glosses = new Map(card.screens.flatMap(s => s.words).filter(w => w.gloss).map(w => [w.id, w.gloss]));
  for (const grp of P.GROUPS) {
    const names = grp.word ? ['none', 'everyday', 'understands'] : ['none', 'vague', 'understands'];
    const results = grp.ids.map(id => (items.get(id) || {}).result || 'none');
    const counts = names.map(n => results.filter(r => r === n).length);
    p.knowledge[grp.key] = counts.indexOf(Math.max(...counts));
    grp.ids.forEach((id, i) => {
      if (results[i] === names[p.knowledge[grp.key]]) return;
      const o = {result: results[i]};
      if (results[i] === 'other') o.gloss = glosses.get(id) || items.get(id).gloss || 'A mistaken meaning';
      p.overrides[id] = o;
    });
  }
  return P.validate(p);
}

/* side sheet: open any persona; edit the ones made here */
let sheetFor = null, sheetCopy = null, sheetDirty = false, preselect = null;
function openSheet(id) {
  sheetFor = S.personas.find(p => p.id === id); if (!sheetFor) return;
  const editable = !!sheetFor.parameters;
  sheetCopy = editable ? {p: clone(sheetFor.parameters), description: sheetFor.description} : null; sheetDirty = false;
  $('#sheet-body').innerHTML = `<div class="row" style="margin:8px 0 4px">${avatar(sheetFor, 56)}<div style="flex:1;min-width:0">
      ${editable ? `<md-outlined-text-field id="sheet-name" label="Name" value="${esc(sheetFor.name)}" style="width:100%"></md-outlined-text-field>` : `<h2>${esc(sheetFor.name)}</h2>`}</div></div>
    <p class="muted small" style="margin:10px 0 2px">${kindLabel(sheetFor)}</p>
    ${sheetFor.description ? `<p style="margin:0 0 4px">“${esc(sheetFor.description)}”</p>` : ''}
    <div class="chips" id="sheet-chips" style="margin-bottom:12px">${chipsFor(sheetFor.scores, sheetFor.known, (sheetFor.parameters || {}).humanFactors)}</div>
    ${sheetFor.from === 'questionnaire' ? '<div class="banner info"><span class="ms">fact_check</span><div>Everything starts where their answers put them. What you change replaces only that part; the rest stays as their answers built it.</div></div>' : ''}
    ${editable ? editorHTML(sheetCopy.p, true) : '<div class="banner bad"><span class="ms">error</span><div>This persona has no settings to edit. Delete it and create it again.</div></div>'}`;
  $('#sheet-dup').hidden = !editable;
  $('#sheet-cancel').hidden = $('#sheet-save').hidden = !editable;
  markSheetDirty(false);
  $('#sheet').hidden = false;
  requestAnimationFrame(() => { $('#sheet').classList.add('show'); $('#scrim').classList.add('show'); });
}
function closeSheet() { $('#sheet').classList.remove('show'); $('#scrim').classList.remove('show'); setTimeout(() => { $('#sheet').hidden = true; }, 300); sheetFor = sheetCopy = null; }
function tryClose() { if (sheetDirty) $('#discard-dialog').show(); else closeSheet(); }
function markSheetDirty(on) { sheetDirty = on; $('#sheet-save').disabled = !on; $('#sheet-title').innerHTML = (sheetCopy ? 'Edit persona' : 'Persona') + (on ? '<span class="dirty-dot" title="Unsaved changes"></span>' : ''); }
async function saveSheet() {
  const p = sheetCopy.p; p.name = ($('#sheet-name').value || '').trim() || p.name;
  const bundle = buildBundle(p);
  const before = {id: sheetFor.id, parameters: clone(sheetFor.parameters), description: sheetFor.description};
  await api('/api/personas/update', {id: sheetFor.id, ...bundle, description: sheetCopy.description});
  closeSheet(); await render();
  snack(`Saved “${p.name}”`, async () => { try { await api('/api/personas/update', {id: before.id, ...buildBundle(before.parameters), description: before.description}); render(); } catch (e) { fail(e); } });
}
function editing(el) { const root = el.closest('[data-editor]'); return root && (root.dataset.editor === 'sheet' ? sheetCopy && sheetCopy.p : draft && draft.p); }
function refreshChips(el) {
  const root = el.closest('[data-editor]');
  if (root && root.dataset.editor === 'sheet') { $('#sheet-chips').innerHTML = chipsFor(scoresOf(sheetCopy.p), knownOf(sheetCopy.p), sheetCopy.p.humanFactors); markSheetDirty(true); }
  else if ($('#sum-chips') && draft) $('#sum-chips').innerHTML = chipsFor(scoresOf(draft.p), knownOf(draft.p), draft.p.humanFactors);
}

/* ---- run a test ---- */
let runs = 5;
pages.run = async () => {
  await loadPersonas();
  const w = currentWf() || {}, ready = w.status && w.status.key === 'ready';
  const pick = p => `<label class="pick"><md-checkbox touch-target="wrapper" data-pick="${esc(p.id)}" ${p.kind !== 'self' && (!preselect || preselect === p.id) ? 'checked' : ''}></md-checkbox>${avatar(p, 40)}<div style="flex:1;min-width:0"><div>${esc(p.name)}</div><div class="muted small">${kindLabel(p)}</div></div></label>`;
  return `<div class="page">
    <div class="page-head"><div><h1>Run a test</h1><p class="muted">Each persona runs several times, so you see how often a problem happens.</p></div></div>
    ${ready ? '' : `<div class="banner bad"><span class="ms">block</span><div>${esc(w.name || 'This workflow')} is not ready to test. <a href="#test/${esc(w.id)}">Finish setting it up</a> first.</div></div>`}
    <div class="run-grid">
      <div class="stack">
        <div class="card"><div class="row" style="justify-content:space-between"><div style="min-width:0"><h3>${esc(w.name || 'Workflow')}</h3><p class="muted small" style="margin:4px 0 0">${esc(String(w.task || '').split(/(?<=[.!?])\s/)[0])}</p></div><md-outlined-button id="change-flow">Change</md-outlined-button></div></div>
        <div class="card"><h3 style="margin-bottom:8px">Who takes part</h3>
          ${S.personas.map(pick).join('') || '<p class="muted">No personas yet. <a href="#new">Describe one</a>.</p>'}
        </div>
        <div class="card"><div class="row" style="justify-content:space-between;flex-wrap:wrap"><div><h3>Runs per persona</h3><p class="muted small" style="margin:4px 0 0">More runs give steadier rates. 5 is a good start.</p></div>
          <div class="stepper"><md-outlined-icon-button id="runs-minus" aria-label="Fewer runs"><span class="ms">remove</span></md-outlined-icon-button><span id="runs-n" style="font:400 22px var(--md-ref-typeface-brand);width:40px;text-align:center">${runs}</span><md-outlined-icon-button id="runs-plus" aria-label="More runs"><span class="ms">add</span></md-outlined-icon-button></div></div></div>
      </div>
      <div class="card tonal summary"><h3>Summary</h3><p id="run-summary" class="muted"></p>
        <md-filled-button id="start-run" style="width:100%" ${ready ? '' : 'disabled'}><span slot="icon" class="ms">play_arrow</span>Start test</md-filled-button>
        <p class="small muted" style="margin:12px 0 0">You can leave this page while it runs.</p></div>
    </div>
    <div id="progress-area"></div></div>`;
};
function setupRun() {
  const ready = (currentWf() || {}).status && currentWf().status.key === 'ready';
  const chosen = () => $$('[data-pick]').filter(c => c.checked).map(c => c.dataset.pick);
  const summary = () => {
    const n = chosen().length;
    $('#run-summary').innerHTML = n ? `${n} persona${n > 1 ? 's' : ''} × ${runs} runs = <b>${n * runs} runs</b>, about ${n * runs * 3} minutes.` : 'Choose at least one persona.';
    $('#start-run').disabled = !n || !ready || !!S.runJob;
  };
  $('#runs-minus').addEventListener('click', () => { runs = Math.max(1, runs - 1); $('#runs-n').textContent = runs; summary(); });
  $('#runs-plus').addEventListener('click', () => { runs = Math.min(10, runs + 1); $('#runs-n').textContent = runs; summary(); });
  $$('[data-pick]').forEach(c => c.addEventListener('change', summary));
  $('#change-flow').addEventListener('click', openPicker);
  $('#start-run').addEventListener('click', async () => {
    try { const r = await api('/api/tests/start', {cards: chosen(), runs}); S.runJob = {id: r.id, cards: chosen(), runs}; showProgress(); } catch (e) { fail(e); }
  });
  preselect = null;
  summary();
  if (S.runJob) return showProgress();
  // A test started before this page was opened (or before a reload): pick it up.
  api('/api/status').then(async st => {
    if (!st.activeJob || S.runJob) return;
    const j = await api(`/api/wjob?id=${st.activeJob}`).catch(() => null);
    if (j && j.kind === 'run' && j.state === 'running' && j.view.cards) { S.runJob = {id: j.id, cards: j.view.cards, runs: j.view.runs}; showProgress(); }
  }).catch(() => {});
}
const nameOf = id => ([...S.personas, ...S.selfTest].find(p => p.id === id) || {name: id}).name;
function showProgress() {
  const job = S.runJob; if (!job || !$('#progress-area')) return;
  $('#progress-area').innerHTML = `<div class="card" style="margin-top:24px"><div class="row" style="justify-content:space-between;flex-wrap:wrap"><h2>Running</h2>
      <div class="row"><span class="muted small" id="eta"></span><md-text-button id="stop-run">Stop</md-text-button></div></div>
    <md-linear-progress id="overall" value="0" style="margin:16px 0 8px"></md-linear-progress>
    ${job.cards.map(c => `<div class="livecard">${avatar({id: c, name: nameOf(c)}, 40)}<div style="min-width:0"><div>${esc(nameOf(c))}</div><div class="muted small" data-status="${esc(c)}">Waiting</div>
      <div class="dots" data-dots="${esc(c)}">${Array.from({length: job.runs}, () => '<span></span>').join('')}</div></div>
      <md-text-button class="watch-btn" data-watch="${esc(c)}"><span slot="icon" class="ms">visibility</span>Watch live</md-text-button></div>`).join('')}</div>`;
  $('#stop-run').addEventListener('click', async () => { try { await api('/api/jobs/stop', {id: job.id}); } catch (e) { fail(e); } });
  pollRun();
}
let runTimer;
async function pollRun() {
  clearTimeout(runTimer);
  const job = S.runJob; if (!job) return;
  try {
    const j = await api(`/api/wjob?id=${job.id}`), v = j.view, total = job.cards.length * job.runs;
    if ($('#overall')) {
      $('#overall').value = v.done.length / total;
      for (const c of job.cards) {
        const dots = document.querySelector(`[data-dots="${CSS.escape(c)}"]`); if (!dots) continue;
        [...dots.children].forEach((d, i) => { const r = v.done.find(x => x.card === c && x.run === i + 1); d.className = r ? (r.pass ? 'ok' : 'fail') : (v.current && v.current.card === c && v.current.run === i + 1 ? 'now' : ''); });
        const st = document.querySelector(`[data-status="${CSS.escape(c)}"]`);
        if (v.current && v.current.card === c) st.textContent = `Run ${v.current.run} of ${job.runs} · step ${v.current.step} on ${v.current.route || 'the start page'}`;
        else if (v.done.filter(x => x.card === c).length === job.runs) st.textContent = `Done · ${v.done.filter(x => x.card === c && x.pass).length} of ${job.runs} passed`;
      }
      const left = (total - v.done.length) * 3; $('#eta').textContent = j.state === 'running' ? (left ? `About ${left} minutes left` : 'Wrapping up…') : '';
    }
    if (j.state === 'running') { runTimer = setTimeout(pollRun, 2000); return; }
    S.runJob = null;
    if (j.state === 'completed' && v.batch) { const failed = v.done.filter(x => !x.pass).length; snack(`Test finished · ${v.done.length} runs, ${failed} did not pass.`); go('result/' + v.batch); }
    else snack(j.state === 'stopped' ? 'Test stopped.' : `The test failed: ${v.error || 'see the log'}`);
  } catch (e) { fail(e); runTimer = setTimeout(pollRun, 4000); }
}
let liveTimer;
const LIVE = {frame: -1, click: 0, dir: null, on: false};
function placeLive(st) {
  // Coordinates are the engine's window; the screen box keeps its shape, so percentages place them.
  const W0 = st.width || 1440, H0 = st.height || 844, pct = (v, of) => `${(v / of) * 100}%`;
  $('#live-screen').style.aspectRatio = `${W0} / ${H0}`;
  $('#live-screen').style.setProperty('--ratio', String(W0 / H0));
  const p = $('#live-pointer'); p.style.left = pct(st.x, W0); p.style.top = pct(st.y, H0);
  if (st.click !== LIVE.click) {
    LIVE.click = st.click;
    const r = $('#live-ripple'); r.style.left = pct(st.cx, W0); r.style.top = pct(st.cy, H0);
    r.classList.remove('go'); void r.offsetWidth; r.classList.add('go');
  }
  const f = $('#live-focus'), rect = st.focus;
  f.hidden = !rect;
  if (rect) Object.assign(f.style, {left: pct(rect.x, W0), top: pct(rect.y, H0), width: pct(rect.w, W0), height: pct(rect.h, H0)});
  $('#live-phase').textContent = st.phase || '';
}
async function openLive() {
  const job = S.runJob; if (!job) return snack('Nothing is running right now.');
  LIVE.frame = -1; LIVE.dir = null; LIVE.on = true;  // the dialog's own open flag comes a moment after show()
  $('#live-dialog').show();
  const tick = async () => {
    if (!LIVE.on) return;
    try {
      const v = await api(`/api/live?id=${job.id}`);
      $('#live-title').textContent = v.card ? `Watching · ${v.card} · run ${v.seed}` : 'Watching the run';
      if (v.dir !== LIVE.dir) { LIVE.dir = v.dir; LIVE.frame = -1; LIVE.click = (v.state || {}).click || 0; }
      const st = v.state;
      if (v.frame && (!st || st.frame !== LIVE.frame)) {
        LIVE.frame = st ? st.frame : LIVE.frame + 1;
        const img = $('#live-img'), next = new Image();
        next.onload = () => { img.src = next.src; img.hidden = false; $('#live-wait').hidden = true; };
        next.src = `${v.frame}?f=${LIVE.frame}-${Date.now()}`;
      }
      if (st) placeLive(st);
      $('#live-log').innerHTML = (v.steps || []).slice().reverse().map(s => `<div><b>Step ${s.step}</b> · ${esc(s.did || 'looking')}
        ${s.why ? `<div class="small" style="margin-top:2px">“${esc(s.why)}”</div>` : ''}<div class="muted small">${esc(s.rule || '')}</div></div>`).join('') || '<div>Opening the product…</div>';
    } catch (e) { /* between runs */ }
    liveTimer = setTimeout(tick, 300);
  };
  tick();
}
function toggleLiveSize() {
  const d = $('#live-dialog'), big = !d.classList.contains('big');
  d.classList.toggle('big', big);
  $('#live-size').innerHTML = `<span class="ms">${big ? 'close_fullscreen' : 'open_in_full'}</span>`;
  $('#live-size').setAttribute('aria-label', big ? 'Make smaller' : 'Enlarge'); $('#live-size').title = big ? 'Make smaller' : 'Enlarge';
}

/* ---- results ---- */
const GRADE_LABEL = () => ((S.flow || {}).engine || {}).grading || {};
pages.results = async () => {
  await loadResults();
  if (!S.results.length) return `<div class="page"><div class="page-head"><div><h1>Results</h1></div></div>
    <div class="card empty"><span class="ms">insights</span><h2>No results for this workflow yet</h2><p class="muted">Run a test and the problems it finds show up here.</p>
    <md-filled-button data-go="run"><span slot="icon" class="ms">play_arrow</span>Run a test</md-filled-button></div></div>`;
  return pages.result(S.results[0].id);
};
let RES = null;
/* What happened at a step of the task in one run, as the researcher reads it. */
const STATUS = {
  ok: {icon: 'check_circle', label: 'Smooth', cls: 'ok'},
  hesitated: {icon: 'help', label: 'Hesitated', cls: 'warn'},
  wrong: {icon: 'error', label: 'Went wrong', cls: 'bad'},
  stopped: {icon: 'block', label: 'Stopped here', cls: 'stop'},
  skipped: {icon: 'remove', label: 'Not reached', cls: 'skip'},
};
const TROUBLE = new Set(['wrong', 'stopped']);
function statusIcon(st, title) { const s = STATUS[st] || STATUS.skipped; return `<span class="jstat ${s.cls}" title="${esc(title || s.label)}"><span class="ms">${s.icon}</span></span>`; }
function stepTrouble(i) {
  const runs = RES.all.filter(r => r.path), at = r => r.path[i] || {};
  return {trouble: runs.filter(r => TROUBLE.has(at(r).status)), hesitated: runs.filter(r => at(r).status === 'hesitated')};
}
pages.result = async (id) => {
  if (!S.results.length) await loadResults();
  RES = await api(`/api/result?id=${encodeURIComponent(id)}`);
  RES.all = RES.cards.flatMap(c => c.runList.map((r, i) => ({...r, name: c.name, card: c.card, n: i + 1})));
  const all = RES.all, N = all.length, passed = all.filter(r => (r.evaluation || {}).overall).length;
  // The step that went wrong most often, then the one people hesitated at most.
  const ranked = RES.steps.map((s, i) => ({i, s, ...stepTrouble(i)})).sort((a, b) => b.trouble.length - a.trouble.length || b.hesitated.length - a.hesitated.length);
  const worst = ranked[0] && (ranked[0].trouble.length || ranked[0].hesitated.length) ? ranked[0] : null;
  const earlier = S.results.filter(r => r.id !== id).slice(0, 8);
  const persons = [...new Set(all.map(r => r.name))];
  return `<div class="page">
    <div class="page-head"><div><h1>Results</h1><p class="muted">${esc(RES.workflow)} · ${esc(persons.join(', '))} · ${N} run${N === 1 ? '' : 's'} · ${esc(when(RES.at))}</p></div>
      <div class="actions">${earlier.length ? `<md-outlined-select id="res-pick" label="Earlier tests" style="min-width:220px">${S.results.map(r => `<md-select-option value="${r.id}" ${r.id === id ? 'selected' : ''}><div slot="headline">${esc(when(r.at))} · ${r.runs} runs</div></md-select-option>`).join('')}</md-outlined-select>` : ''}
        <md-filled-tonal-button data-go="run"><span slot="icon" class="ms">replay</span>Run again</md-filled-tonal-button></div></div>
    <div class="card headline" style="margin-bottom:16px">
      <div class="big" style="${passed === N ? 'color:var(--md-sys-color-tertiary)' : ''}">${passed} of ${N}</div>
      <div><p class="insight" style="margin:0 0 6px">${passed === N ? 'runs did the task right.' : `runs did the task right; ${N - passed} did not.`}</p>
        <p class="muted" style="margin:0">${worst ? (worst.trouble.length
          ? `The most trouble was at step ${worst.i + 1}, “${esc(worst.s.action)}”: ${worst.trouble.length} of ${N} runs went wrong or stopped there.`
          : `Nothing went wrong; people hesitated most at step ${worst.i + 1}, “${esc(worst.s.action)}”.`) : 'Every run went through every step smoothly.'}</p>
        ${worst ? `<md-text-button data-jopen="${worst.i}" style="margin:8px 0 0 -12px">See what happened at step ${worst.i + 1}<span slot="icon" class="ms">arrow_downward</span></md-text-button>` : ''}</div></div>
    <div class="tabs-wrap"><md-tabs id="res-tabs"><md-primary-tab>Step by step</md-primary-tab><md-primary-tab>By persona</md-primary-tab><md-primary-tab>Every run</md-primary-tab></md-tabs></div>
    <div id="res-body">${resultsBody(0)}</div></div>`;
};
function journeyHTML() {
  const runs = RES.all.filter(r => r.path), N = RES.all.length;
  if (!runs.length) return '<div class="card empty"><span class="ms">insights</span><h2>No step-by-step record</h2><p class="muted">These runs were made before steps were recorded. Run the test again.</p></div>';
  const legend = ['ok', 'hesitated', 'wrong', 'stopped', 'skipped'].map(k => `<span class="row small" style="gap:6px">${statusIcon(k)}${STATUS[k].label}</span>`).join('');
  return `<div class="card" style="padding:0">
    <div class="row" style="flex-wrap:wrap;gap:16px;padding:16px 20px 8px">${legend}</div>
    <div class="jwrap"><table class="journey">
      <thead><tr><th class="jstep">The task, step by step</th>${runs.map(r => `<th class="jrun" title="${esc(r.name)} · run ${r.n}">${avatar({id: r.card, name: r.name}, 28)}<div class="small muted">${esc(r.name)}${runs.filter(x => x.card === r.card).length > 1 ? ` · ${r.n}` : ''}</div></th>`).join('')}<th class="jcount">Went wrong</th></tr></thead>
      <tbody>${RES.steps.map((s, i) => { const t = stepTrouble(i);
        return `<tr class="jrow ${t.trouble.length ? 'has' : t.hesitated.length ? 'some' : ''}" data-jstep="${i}" tabindex="0" aria-expanded="false">
          <td class="jstep"><span class="n">${i + 1}</span><span>${esc(s.action)}</span><span class="ms chev">expand_more</span></td>
          ${runs.map(r => `<td class="jcell">${statusIcon((r.path[i] || {}).status, `${r.name} · run ${r.n}: ${(STATUS[(r.path[i] || {}).status] || STATUS.skipped).label}`)}</td>`).join('')}
          <td class="jcount">${t.trouble.length ? `<b>${t.trouble.length}</b> of ${N}` : t.hesitated.length ? `<span class="muted">${t.hesitated.length} hesitated</span>` : '<span class="muted">none</span>'}</td></tr>
        <tr class="jdetail" id="jd-${i}" hidden><td colspan="${runs.length + 2}"></td></tr>`; }).join('')}</tbody></table></div></div>`;
}
/* Everything that happened at one step: per run with trouble, the screen they saw, where they
   clicked, what they were thinking, and what should have happened. */
function stepDetailHTML(i) {
  const s = RES.steps[i], runs = RES.all.filter(r => r.path && !['ok', 'skipped'].includes((r.path[i] || {}).status));
  const head = s.hard ? `<div class="banner info" style="margin:0 0 12px"><span class="ms">lightbulb</span><div><b>Easy to get wrong here:</b> ${esc(s.hard)}</div></div>` : '';
  if (!runs.length) return `${head}<p class="muted" style="margin:4px 0">Every run that reached this step got through it smoothly.</p>`;
  return head + runs.map(r => {
    const p = r.path[i], st = STATUS[p.status];
    const what = [
      ...p.missed.map(m => `<li><b>Left “${esc(m.text)}” as it was.</b> ${m.why ? `What the task needed: ${esc(m.why)}` : ''}</li>`),
      ...p.failed.map(f => `<li><b>Not right at the end:</b> ${esc(f.text)}${f.detail ? ` <span class="muted">(${esc(f.detail)})</span>` : ''}</li>`),
      ...(p.stopped ? [`<li><b>Stopped here:</b> ${esc((r.stop || {}).why || (r.stop || {}).reason || '')}</li>`] : []),
      ...(p.wrong ? [`<li>Took ${p.wrong} wrong turn${p.wrong > 1 ? 's' : ''}</li>`] : []),
      ...(p.backs ? [`<li>Went back ${p.backs} time${p.backs > 1 ? 's' : ''}</li>`] : []),
      ...(p.slips ? [`<li>Missed what they meant to click ${p.slips} time${p.slips > 1 ? 's' : ''}</li>`] : []),
    ];
    const key = p.moves.find(m => m.misclick) || p.moves[p.moves.length - 1];
    return `<div class="jcase">
      <div class="row" style="gap:10px;flex-wrap:wrap">${avatar({id: r.card, name: r.name}, 32)}<b>${esc(r.name)}</b><span class="muted small">run ${r.n}</span><span class="tag ${st.cls === 'warn' ? 'amber' : st.cls === 'ok' ? 'green' : 'red'}"><span class="ms">${st.icon}</span>${st.label}</span>
        <span class="grow"></span>${r.report ? `<md-text-button href="${r.report}" target="_blank"><span slot="icon" class="ms">play_circle</span>Watch the whole run</md-text-button>` : ''}</div>
      <div class="jcase-body">
        ${key && key.shot ? `<figure class="jshot">${shotCrop(key.shot, key.size, key.box, `What ${r.name} saw at step ${i + 1}`, 900)}
          <figcaption class="small muted">What they saw when they ${esc(key.did.charAt(0).toLowerCase() + key.did.slice(1))}${key.box ? '; the ring is where they clicked' : ''}. Click to see the whole screen.</figcaption></figure>` : ''}
        <div style="min-width:0">
          ${what.length ? `<ul class="jwhat">${what.join('')}</ul>` : ''}
          <h4 style="margin:12px 0 6px">What they did and thought</h4>
          <ol class="jmoves">${p.moves.map(m => `<li><span>${esc(m.did)}</span>${m.why ? `<div class="small" style="margin-top:2px">“${esc(m.why)}”</div>` : ''}</li>`).join('') || '<li class="muted">Nothing: they did not act on this step.</li>'}</ol>
        </div></div></div>`;
  }).join('');
}
function placeMark(img) {
  const box = JSON.parse(img.dataset.box || 'null'), mark = img.parentElement.querySelector('.mark');
  if (!box || !mark || !img.naturalWidth) return;
  const W = img.naturalWidth, H = img.naturalHeight, cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  if (cx > W || cy > H) return;
  Object.assign(mark.style, {left: `${cx / W * 100}%`, top: `${cy / H * 100}%`}); mark.hidden = false;
}
function toggleJourneyStep(i, force) {
  const row = document.querySelector(`.jrow[data-jstep="${i}"]`), det = $(`#jd-${i}`); if (!row || !det) return;
  const open = force ?? det.hidden;
  det.hidden = !open; row.setAttribute('aria-expanded', String(open)); row.classList.toggle('open', open);
  if (open) {
    det.firstElementChild.innerHTML = stepDetailHTML(i);
  }
}
function resultsBody(tab) {
  const all = RES.all, N = all.length;
  if (tab === 0) return journeyHTML();
  if (tab === 1) {
    const labels = GRADE_LABEL(), off = new Set((((S.flow || {}).engine || {}).gradingIgnored) || []);
    const checks = [...new Set(all.flatMap(r => Object.keys((r.evaluation || {}).criteria || {})))];
    return `<div class="card" style="overflow-x:auto"><table class="matrix"><tr><th>What must be right at the end</th>${RES.cards.map(c => `<th><span class="row" style="gap:8px">${avatar({id: c.card, name: c.name}, 28)}${esc(c.name)}</span></th>`).join('')}</tr>
      ${checks.map(k => `<tr><td>${esc(labels[k] || k)}${off.has(k) ? ' <span class="muted small">(not counted)</span>' : ''}</td>${RES.cards.map(c => { const n = c.runList.filter(r => ((r.evaluation || {}).criteria || {})[k]).length, ok = n === c.runList.length;
        return `<td><span class="cell ${ok ? 'ok' : 'bad'}"><span class="ms">${ok ? 'check_circle' : 'error'}</span>${n} of ${c.runList.length}</span></td>`; }).join('')}</tr>`).join('')}
      <tr><td><b>Did the task right</b></td>${RES.cards.map(c => `<td><b>${c.runList.filter(r => (r.evaluation || {}).overall).length} of ${c.runList.length}</b></td>`).join('')}</tr></table></div>`;
  }
  return `<div class="card"><md-list style="background:transparent">${all.map(r => { const pass = (r.evaluation || {}).overall;
    const where = (r.path || []).map((p, i) => TROUBLE.has(p.status) ? i + 1 : null).filter(Boolean);
    return `<md-list-item type="link" href="${r.report || '#'}" target="_blank"><span slot="start">${avatar({id: r.card, name: r.name}, 32)}</span>
      <div slot="headline">${esc(r.name)} · run ${r.n}</div>
      <div slot="supporting-text">${pass ? 'Did the task right' : where.length ? `Went wrong at step ${where.join(', ')}` : esc((r.stop || {}).why || 'Did not finish')} · ${r.actions} actions${r.seconds ? ` · ${Math.round(r.seconds / 60)} min` : ''}
        ${r.path ? `<div class="jstrip">${r.path.map((p, i) => statusIcon(p.status, `Step ${i + 1}: ${(STATUS[p.status] || STATUS.skipped).label}`)).join('')}</div>` : ''}</div>
      <span slot="end" class="ms ${pass ? 'ok' : 'bad'}">${pass ? 'check_circle' : 'error'}</span></md-list-item>`; }).join('')}</md-list></div>`;
}

/* ---------------- workflow picker ---------------- */
function openPicker() {
  $('#workflow-list').innerHTML = S.workflows.map(w => `<md-list-item type="button" data-flow="${esc(w.id)}" ${w.steps ? '' : 'disabled'}><span slot="start" class="ms">account_tree</span>
    <div slot="headline">${esc(w.name)}</div><div slot="supporting-text">${esc(w.status.label)} · ${w.items} knowledge items</div>${w.current ? '<span slot="end" class="ms" style="color:var(--md-sys-color-primary)">check</span>' : ''}</md-list-item>`).join('')
    + '<md-list-item type="button" data-go="new-test"><span slot="start" class="ms">add</span><div slot="headline">New test</div><div slot="supporting-text">Do a task once on any web product</div></md-list-item>';
  $('#workflow-dialog').show();
}
async function useWorkflow(id) {
  await api('/api/workflows/select', {id});
  location.reload();  // the persona builder and the knowledge groups follow the workflow
}

/* ---------------- router ---------------- */
function go(name) { location.hash = name; }
let rendering = 0;
async function render() {
  const n = ++rendering;
  let [name, arg] = (location.hash || '#home').slice(1).split('/');
  name = {workflows: 'tests', 'new-workflow': 'new-test', workflow: 'test'}[name] || name;  // the old pages are gone
  const page = pages[name] ? name : 'home';
  if (!(name === 'workflow' && arg === W.id)) { W.picking = null; }
  try {
    const html = await pages[page](arg && decodeURIComponent(arg));
    if (n !== rendering) return;
    $('#main').innerHTML = html;
  } catch (e) { $('#main').innerHTML = `<div class="page"><div class="banner bad" style="margin-top:24px"><span class="ms">error</span><div>${esc(e.message)}</div></div></div>`; return; }
  const nav = {new: 'personas', workflow: 'tests', 'new-test': 'tests', test: 'tests', result: 'results'}[page] || page;
  $$('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === nav));
  if (page === 'new' || page === 'home') setupComposer();
  if (page === 'run') setupRun();
  if (page === 'results' || page === 'result') {
    const tabs = $('#res-tabs'); if (tabs) tabs.addEventListener('change', e => { $('#res-body').innerHTML = resultsBody(e.target.activeTabIndex); });
    const pick = $('#res-pick'); if (pick) pick.addEventListener('change', () => go('result/' + pick.value));
  }
  if (page === 'workflow') { const t = $('#wf-tabs'); if (t) t.addEventListener('change', e => { W.tab = e.target.activeTabIndex; W.picking = null; rerenderTab(); }); }
  if ($('#b-login-on')) { const sw = $('#b-login-on'); if (sw) sw.addEventListener('change', () => { $('#b-login').hidden = !sw.selected; }); }
}

/* ---------------- events ---------------- */
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-signin],[data-test-edit],#create-test,#save-test,[data-go],[data-open],[data-remove],[data-act],[data-know],[data-english],[data-group-default],[data-state-of],[data-pick-state],.watch-btn,#create,#create-run,#rail-fab,#workflow-pick,#help-btn,#live-close,#live-size,#workflow-close,[data-flow],#scrim,#sheet-close,#sheet-cancel,#sheet-save,#sheet-dup,#sheet-run,#discard-keep,#discard-yes,#save-basics');
  if (!t) return;
  try {
    if (t.matches('[data-signin]')) {
      t.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === t));
      $('#signin-form').hidden = t.dataset.signin !== 'form';
      $('#signin-note').textContent = {hand: 'For single sign-on or a second step: you sign in once in the recording window and the runs reuse it.',
        form: 'The engine signs in with this test account before every run.', none: 'The product opens without signing in.'}[t.dataset.signin];
      return;
    }
    if (t.matches('[data-test-edit]')) { T.edit = Number(t.dataset.testEdit); return render(); }
    if (t.matches('#create-test')) { const r = await api('/api/workflows/create', readTestForm()); return go('test/' + r.id); }
    if (t.matches('#save-test')) { await api('/api/workflows/basics', {id: T.id, ...readTestForm()}); T.edit = 0; snack('Saved.'); return render(); }
    if (t.matches('[data-act^="test-"],[data-act="signed-in"],[data-act="stop-test-job"],[data-act="save-facts"]')) { e.preventDefault(); return await testAct(t.dataset.act, t); }
    if (t.matches('[data-remove]')) {
      e.stopPropagation();
      const p = S.personas.find(x => x.id === t.dataset.remove);
      await api('/api/personas/delete', {id: p.id}); await render();
      snack(`Deleted “${p.name}”`, async () => { await api('/api/personas/restore', {id: p.id}); render(); });
      return;
    }
    if (t.matches('[data-flow]')) { $('#workflow-dialog').close(); if (t.dataset.flow !== S.current) await useWorkflow(t.dataset.flow); return; }
    if (t.matches('[data-go]')) { $('#workflow-dialog').open && $('#workflow-dialog').close(); return go(t.dataset.go); }
    if (t.matches('#rail-fab')) return go('new');
    if (t.matches('[data-open]')) return openSheet(t.dataset.open);
    if (t.matches('#scrim,#sheet-close,#sheet-cancel')) return tryClose();
    if (t.matches('#discard-keep')) return $('#discard-dialog').close();
    if (t.matches('#discard-yes')) { $('#discard-dialog').close(); return closeSheet(); }
    if (t.matches('#sheet-save')) return await saveSheet();
    if (t.matches('#sheet-dup')) {
      const p = clone(sheetCopy.p); p.name = ('Copy of ' + (($('#sheet-name').value || '').trim() || p.name)).slice(0, 80);
      const r = await api('/api/personas/save', {...buildBundle(p), description: sheetCopy.description});
      closeSheet(); await render();
      snack(`Duplicated as “${p.name}”`, async () => { await api('/api/personas/delete', {id: r.id}); render(); });
      return;
    }
    if (t.matches('#sheet-run')) { const id = sheetFor.id; if (sheetDirty) await saveSheet(); else closeSheet(); preselect = id; return go('run'); }
    if (t.matches('.watch-btn')) return openLive();
    if (t.matches('#live-close')) { LIVE.on = false; clearTimeout(liveTimer); return $('#live-dialog').close(); }
    if (t.matches('#live-size')) return toggleLiveSize();
    if (t.matches('#workflow-pick')) return openPicker();
    if (t.matches('#workflow-close')) return $('#workflow-dialog').close();
    if (t.matches('#help-btn')) return snack('Add a workflow by doing its task once; describe personas in plain words; run; read what went wrong.');
    if (t.matches('[data-know]')) {
      const p = editing(t); if (!p) return;
      PersonaParameters.setGroup(p, t.dataset.know, Number(t.dataset.v));
      t.parentElement.querySelectorAll('button').forEach(b => { const on = b === t; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); });
      return refreshChips(t);
    }
    if (t.matches('[data-english]')) { const p = editing(t); if (!p) return; p.english = t.dataset.english; t.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === t)); return refreshChips(t); }
    if (t.matches('#create,#create-run')) {
      const typed = ($('#p-name').value || '').trim();
      if (draft.kind !== 'description' && !/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(typed)) return snack('Give the participant a code name, such as P4. Their name is never kept.');
      let r, made;
      if (draft.kind === 'answers') {
        r = await api('/api/personas/save-participant', {code: typed, card: draft.card, answers: draft.doc, parameters: paramsFromCard(draft.card, typed)});
        made = r.name;
      } else {
        draft.p.name = typed || draft.p.name;
        r = await api('/api/personas/save', {...buildBundle(draft.p), description: draft.description, source: draft.kind === 'survey' ? 'survey' : undefined});
        made = draft.p.name;
      }
      draft = null;
      snack(`Created “${made}”`, async () => { await api('/api/personas/delete', {id: r.id}); render(); });
      preselect = t.id === 'create-run' ? r.id : null;
      return go(t.id === 'create-run' ? 'run' : 'personas');
    }
    if (t.matches('#save-basics')) { await api('/api/workflows/basics', {id: W.id, ...readBasics()}); $('#confirm-dialog').close(); snack('Product details saved.'); W.edit = null; return render(); }
    if (t.matches('[data-state-of]')) { W.stepState[t.dataset.stateOf] = Number(t.dataset.state); return rerenderTab(); }
    if (t.matches('[data-pick-state]')) {
      const it = W.edit.items.find(i => i.id === W.picking.item), step = W.edit.steps.find(s => s.id === it.step);
      const r = await api('/api/workflows/pick', {id: W.id, state: Number(t.dataset.pickState), control: Number(t.dataset.pickControl)});
      it.locate = r.locate; if (r.route !== routeOfScreen(step.screen)) it.locate.route = r.route;
      W.picking = null; markDirtyFlow(); return rerenderTab();
    }
    if (t.matches('[data-group-default]')) { W.edit.knowledgeGroups[Number(t.dataset.groupDefault)].default = Number(t.dataset.v); markDirtyFlow(); return rerenderTab(); }
    if (t.matches('[data-act]')) return await act(t.dataset.act, t, e);
  } catch (err) { fail(err); }
});
async function act(name, t, e) {
  const f = W.edit;
  switch (name) {
    case 'record': {
      if (W.d.flow && !(await confirmBox('Record the task again?', 'The new recording replaces this one. The workflow is drafted again from it; your review edits are kept until then in flow.prev.json.', 'Record'))) return;
      await api('/api/workflows/record', {id: W.id}); snack('A browser window is opening. Do the task there.'); return render();
    }
    case 'draft': await api('/api/workflows/draft', {id: W.id}); return render();
    case 'redraft': if (await confirmBox('Draft again?', 'Gemini drafts the workflow again from the recording. Your edits are replaced (kept in flow.prev.json).', 'Draft')) { await api('/api/workflows/draft', {id: W.id}); W.edit = null; W.dirty = false; return render(); } return;
    case 'stop-job': await api('/api/jobs/stop', {id: W.d.job}); return;
    case 'edit-basics': {
      $('#confirm-title').textContent = 'Product details';
      $('#confirm-text').innerHTML = basicsForm(W.d.basics) + '<div class="actions" style="margin-top:12px"><md-filled-button id="save-basics">Save</md-filled-button></div>';
      $('#confirm-yes').hidden = true; $('#confirm-no').onclick = () => { $('#confirm-dialog').close(); $('#confirm-yes').hidden = false; };
      $('#confirm-dialog').show();
      const sw = $('#b-login-on'); sw.addEventListener('change', () => { $('#b-login').hidden = !sw.selected; });
      return;
    }
    case 'use-wf': return useWorkflow(W.id);
    case 'save-flow': { const r = await api('/api/workflows/save', {id: W.id, flow: strip(f)}); W.dirty = false; snack(r.problems.length ? `Saved, with ${r.problems.length} things to fix.` : 'Saved.'); return render(); }
    case 'confirm-flow': {
      if (W.dirty) { const r = await api('/api/workflows/save', {id: W.id, flow: strip(f)}); W.dirty = false; if (r.problems.length) { snack('Fix the problems listed at the top first.'); return render(); } }
      await api('/api/workflows/check', {id: W.id}); W.tab = 0; return render();
    }
    case 'pick': W.picking = {item: t.dataset.itemId, step: f.items.find(i => i.id === t.dataset.itemId).step}; rerenderTab();
      document.querySelector(`[data-step="${CSS.escape(W.picking.step)}"]`).scrollIntoView({behavior: 'smooth', block: 'start'}); return;
    case 'cancel-pick': e.preventDefault(); W.picking = null; return rerenderTab();
    case 'unpick': { const it = f.items.find(i => i.id === t.dataset.itemId); delete it.locate; markDirtyFlow(); return rerenderTab(); }
    case 'del-item': {
      const id = t.dataset.itemId; f.items = f.items.filter(i => i.id !== id);
      for (const g of f.knowledgeGroups) g.items = g.items.filter(x => x !== id);
      f.knowledgeGroups = f.knowledgeGroups.filter(g => g.items.length);
      for (const k of ['entry', 'help', 'review']) f.engine.items[k] = (f.engine.items[k] || []).filter(x => x !== id);
      markDirtyFlow(); return rerenderTab();
    }
    case 'add-item': {
      const it = {id: nextItemId(), step: t.dataset.stepId, way: null, needed: true, kind: 'concept', text: '', meaning: '', everyday: '', common: '', altOf: null, exps: [], basis: 'Added in review'};
      f.items.push(it); regroup(it); markDirtyFlow(); return rerenderTab();
    }
    case 'add-group': { const word = t.dataset.word === '1'; f.knowledgeGroups.push({key: (word ? 'terms-' : 'knowledge-') + (f.knowledgeGroups.length + 1), title: word ? 'New word group' : 'New knowledge group', word, default: 1, description: 'Added in review', examples: '', items: []}); markDirtyFlow(); return rerenderTab(); }
    case 'add-exp': { const g = f.groups[0]; if (!g) return snack('Add a group of experience first.'); const n = Math.max(0, ...f.experiences.map(x => Number(x.id.slice(1)) || 0)) + 1;
      f.experiences.push({id: 'X' + String(n).padStart(2, '0'), group: g.id, text: '', question: {en: '', zh: ''}}); markDirtyFlow(); return rerenderTab(); }
    case 'del-exp': { const ex = f.experiences.splice(Number(t.dataset.expI), 1)[0]; for (const i of f.items) i.exps = (i.exps || []).filter(x => x !== ex.id); markDirtyFlow(); return rerenderTab(); }
    case 'add-plain': f.checks.push(''); markDirtyFlow(); return rerenderTab();
    case 'del-plain': f.checks.splice(Number(t.dataset.i), 1); markDirtyFlow(); return rerenderTab();
    case 'add-check': f.engine.target.success.push({name: 'New check', type: 'text', url: (f.engine.routes.list || [])[0] || '/', contains: ''}); markDirtyFlow(); return rerenderTab();
    case 'del-check': f.engine.target.success.splice(Number(t.dataset.i), 1); markDirtyFlow(); return rerenderTab();
  }
}
function strip(f) { const out = clone(f); delete out.__id; return out; }
const fieldValue = el => el.matches('md-checkbox') ? el.checked : el.matches('md-switch') ? el.selected : el.value;
document.addEventListener('input', e => {
  const el = e.target;
  if (el.id === 'sheet-name') return markSheetDirty(true);
  const s = el.closest && el.closest('md-slider');
  if (s && s.dataset.trait) {
    const p = editing(s); if (!p) return;
    p[s.dataset.trait] = s.value;
    const r = s.closest('.trait').querySelector(`[data-r="${s.dataset.trait}"]`); const t = TRAITS.find(x => x.key === s.dataset.trait);
    if (r && t) r.textContent = readout(t, s.value);
    return refreshChips(s);
  }
  if (location.hash.startsWith('#workflow/') && W.edit) editFlowField(el);
});
document.addEventListener('change', e => {
  const el = e.target;
  const sw = el.closest && el.closest('md-switch[data-perc]');
  if (sw) { const p = editing(sw); if (!p) return; p.humanFactors[sw.dataset.perc] = sw.selected ? sw.dataset.on : 'unspecified'; return refreshChips(sw); }
  const way = el.closest && el.closest('md-filter-chip[data-way]');
  if (way) return;
  if (location.hash.startsWith('#workflow/') && W.edit) editFlowField(el, true);
});
document.addEventListener('click', e => {
  const chip = e.target.closest && e.target.closest('md-filter-chip[data-way]');
  if (chip) setTimeout(() => { const p = editing(chip); if (!p) return; const on = $$('[data-editor] md-filter-chip[data-way]').filter(c => c.closest('[data-editor]') === chip.closest('[data-editor]') && c.selected).map(c => c.dataset.way);
    if (!on.length) { chip.selected = true; return snack('Keep at least one way of making sure.'); } p.confirmBy = on; refreshChips(chip); });
  const teach = e.target.closest && e.target.closest('md-filter-chip[data-teach]');
  if (teach) setTimeout(() => { const it = W.edit.items.find(i => i.id === teach.dataset.teachItem); const x = teach.dataset.teach;
    it.exps = teach.selected ? [...new Set([...(it.exps || []), x])] : (it.exps || []).filter(v => v !== x); markDirtyFlow(); });
  const sig = e.target.closest && e.target.closest('md-filter-chip[data-signal]');
  if (sig) setTimeout(() => { W.edit.signals[sig.dataset.signal] = sig.selected; markDirtyFlow(); });
});
document.addEventListener('change', e => {
  const sel = e.target.closest && e.target.closest('select[data-move]');
  if (!sel || !W.edit) return;
  const id = sel.dataset.move;
  for (const g of W.edit.knowledgeGroups) g.items = g.items.filter(x => x !== id);
  W.edit.knowledgeGroups[Number(sel.value)].items.push(id);
  markDirtyFlow(); rerenderTab();
});
function editFlowField(el, committed) {
  const f = W.edit, v = fieldValue(el);
  const row = el.closest('[data-item]');
  if (row && el.dataset.field) {
    const it = f.items.find(i => i.id === row.dataset.item); const k = el.dataset.field;
    it[k] = v;
    if (k === 'kind') { if (it.kind !== 'word') it.common = ''; else it.common = it.common || 'none'; regroup(it); if (committed) rerenderTab(); }
    return markDirtyFlow();
  }
  const step = el.closest('[data-step]');
  if (step && el.dataset.stepField) { f.steps.find(s => s.id === step.dataset.step)[el.dataset.stepField] = v; return markDirtyFlow(); }
  const g = el.closest('[data-group]');
  if (g && el.dataset.groupField) { f.knowledgeGroups[Number(g.dataset.group)][el.dataset.groupField] = v; return markDirtyFlow(); }
  const eg = el.closest('[data-egroup]');
  if (eg && el.dataset.egField) { const grp = f.groups[Number(eg.dataset.egroup)]; if (el.dataset.egField === 'source') grp.source = v; else grp.label[el.dataset.egField] = v; return markDirtyFlow(); }
  const ex = el.closest('[data-exp]');
  if (ex && el.dataset.expField) { const x = f.experiences[Number(ex.dataset.exp)]; if (el.dataset.expField === 'text') x.text = v; else x.question[el.dataset.expField] = v; return markDirtyFlow(); }
  if (el.dataset.plain !== undefined) { f.checks[Number(el.dataset.plain)] = v; return markDirtyFlow(); }
  const ck = el.closest('[data-check]');
  if (ck && el.dataset.ck) {
    const c = f.engine.target.success[Number(ck.dataset.check)], k = el.dataset.ck;
    if (k === 'where' || k === 'expect') c[k] = kvParse(v); else if (k === 'list' && !v) delete c.list; else c[k] = v;
    if (k === 'type' && committed) {
      for (const x of ['url', 'list', 'where', 'expect', 'contains', 'matches']) if (x !== 'url') delete c[x];
      if (v === 'json') { c.where = {}; c.expect = {}; } if (v === 'text') c.contains = ''; if (v === 'url') { delete c.url; c.matches = ''; }
      rerenderTab();
    }
    return markDirtyFlow();
  }
  if (el.dataset.eng === 'created') { f.engine.created = v; return markDirtyFlow(); }
  if (el.dataset.eng === 'list') { f.engine.routes.list = v ? [v] : []; return markDirtyFlow(); }
  if (el.dataset.list) { const [a, b] = el.dataset.list.split('.'); f.engine[a] = f.engine[a] || {}; f.engine[a][b] = String(v).split(',').map(x => x.trim()).filter(Boolean); return markDirtyFlow(); }
  if (el.dataset.top) { f[el.dataset.top] = v; return markDirtyFlow(); }
  if (el.dataset.sit) { f.situation = f.situation || {}; f.situation[el.dataset.sit] = v; return markDirtyFlow(); }
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && sheetFor && !$('#discard-dialog').open) tryClose(); });
window.addEventListener('hashchange', render);
document.addEventListener('close', e => { if (e.target && e.target.id === 'live-dialog') { LIVE.on = false; clearTimeout(liveTimer); } }, true);
window.addEventListener('beforeunload', e => { if (W.dirty) { e.preventDefault(); e.returnValue = ''; } });

/* ---------------- start ---------------- */
(async () => {
  try {
    token = (await api('/api/status')).token;
    await loadWorkflows();
    await Promise.all([loadFlow(), waitBuilder()]);
    await customElements.whenDefined('md-filled-button');
  } catch (e) { fail(e); }
  render();
})();

/* results: a step of the task opens to show what happened there */
document.addEventListener('click', e => {
  const open = e.target.closest('[data-jopen]');
  if (open) {
    const i = Number(open.dataset.jopen), tabs = $('#res-tabs');
    if (tabs && tabs.activeTabIndex !== 0) { tabs.activeTabIndex = 0; $('#res-body').innerHTML = resultsBody(0); }
    toggleJourneyStep(i, true);
    document.querySelector(`.jrow[data-jstep="${i}"]`).scrollIntoView({behavior: 'smooth', block: 'start'});
    return;
  }
  const row = e.target.closest('.jrow');
  if (row) toggleJourneyStep(Number(row.dataset.jstep));
});
document.addEventListener('keydown', e => {
  const row = e.target.closest && e.target.closest('.jrow');
  if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleJourneyStep(Number(row.dataset.jstep)); }
});

/* new test from a workflow file */
document.addEventListener('change', async e => {
  if (e.target.id !== 'import-file') return;
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  try {
    let flow;
    try { flow = JSON.parse(await f.text()); } catch (err) { throw Error('That file is not JSON.'); }
    const r = await api('/api/workflows/import', {flow, user: ($('#b-login-user') || {}).value || '', password: ($('#b-login-pass') || {}).value || ''});
    if (!r.needsAccount) await api('/api/workflows/check', {id: r.id});
    snack(r.needsAccount ? 'Imported. Add the test account in step 1, then check it.' : 'Imported. Checking it on your product now.');
    T.edit = r.needsAccount ? 1 : 0; go('test/' + r.id);
  } catch (err) { fail(err); }
});
