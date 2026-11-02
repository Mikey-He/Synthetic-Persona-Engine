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
  return out.slice(0, 2).map(([c, i, t]) => `<span class="tag ${c}"><span class="ms">${i}</span>${t}</span>`).join('');
}
const KIND_LABEL = {studio: 'From a description', questionnaire: "From a participant's questionnaire", survey: "From a participant's survey or interview"};
const kindLabel = p => KIND_LABEL[p.from || p.kind] || '';
/* A setting's name as the researcher knows it, for the list of what the survey did not say. */
function settingName(path) {
  const [head, key] = path.split('.');
  if (head === 'knowledge') return 'What they know: ' + ((groupsVisible().find(g => g.key === key) || {}).title || key);
  if (head === 'humanFactors') return ({colorVision: 'Colour vision', clickPrecision: 'Clicking small targets',
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
/* ---------------- loading ---------------- */
async function loadWorkflows() {
  const data = await api('/api/workflows');
  S.workflows = data.workflows; S.current = data.current;
  const w = currentWf();
  const wl = $('#workflow-label'); if (wl) wl.textContent = w ? w.name : 'Choose a workflow';
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
/* The one workflow this platform tests, read-only (2026-11-01). */
pages.workflow = async () => {
  const b = await api('/api/billing');
  const li = (xs, f) => xs.map(x => `<li>${f(x)}</li>`).join('');
  return `<div class="page" style="max-width:960px">
    <div class="page-head"><div><h1>${esc(b.name)}</h1><p class="muted">The one workflow this platform tests. Personas run it; the results are read against the people who did it.</p></div></div>
    <div class="card"><h2>The task, as the participant reads it</h2><p style="white-space:pre-wrap;margin:12px 0">${esc(b.task)}</p><p class="muted small" style="margin:0">Product: <a href="${esc(b.start)}" target="_blank" rel="noopener">${esc(b.start)}</a></p></div>
    <div class="card"><h2>The steps of the task</h2><ol style="margin:12px 0 0;padding-left:22px;line-height:1.7">${li(b.steps, s => esc(s.action))}</ol>
      <p class="muted small" style="margin:12px 0 0">Results are read by the parts of the form: ${b.parts.map(esc).join(' → ')}; before the form and after the save count as parts too.</p></div>
    <div class="card"><h2>What must be right at the end</h2><ul style="margin:12px 0 0;padding-left:22px;line-height:1.7">${li(b.checks, esc)}</ul></div>
    <div class="card"><h2>Where the task can be read more than one way</h2><p class="muted small" style="margin:6px 0 12px">Listed once from the task text. Each run draws one reading per fork; a careful persona may think again on the screen that bears on it.</p>
      ${b.readings.map(r => `<div class="knowrow"><div style="min-width:0"><h3>${esc(r.about)}</h3><ul style="margin:6px 0 0;padding-left:20px" class="muted small">${li(r.options, esc)}</ul></div></div>`).join('') || '<p class="muted">None listed.</p>'}</div>
  </div>`;
};
/* ---- the product details form (Advanced settings) ---- */
/* ---- Advanced settings: every part of a test's flow, for review by hand ---- */
/* -- review: the draft, part by part -- */
/* locators, as sue/locate.py and page_script.js read them */
const LEVEL_WORDS = {true: ['Unknown','Everyday meaning','Knows it'], false: ['Unknown','Vaguely','Knows it']};
/* ---- tests: four steps (approved prototype-new-test.html), each asking only what only the researcher knows ---- */
/* One step of a test. A finished step's title takes you back into it (reopen), as in a stepper:
   it opens as it was set up, and the steps after it fold until it is saved again. */
/* The part of a screenshot around where a step happens, zoomed so its words can be read, with a
   ring on the control. Clicking it opens the whole screen. */
/* A test defined before the four steps (Version A, on our own platform): the same page and the same
   stepper. It was not recorded, so step 2 shows the steps the research team set, each on the screen
   where it happens (from the latest full-card run). Our platform grades the result itself, so
   step 3 chooses which of its checks count towards "done right"; it does not rewrite them. */
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
        <div class="readout">${s.note}</div>${sourceTag(src, s.key)}</div>`).join('')}
    <div class="${box}"><h2>What they know</h2><p class="muted small" style="margin:6px 0 12px">Terms they don't know show up as made-up words, as they would to them.</p>
      ${groupsVisible().map(g => `<div class="knowrow"><div style="min-width:0"><h3>${esc(g.title)}</h3><div class="muted small">${esc(g.examples || g.description)}</div></div>
        <div class="seg" role="radiogroup" aria-label="${esc(g.title)}">${LEVEL_WORDS[!!g.word].map((l, i) =>
          `<button type="button" role="radio" aria-checked="${p.knowledge[g.key] === i}" class="${p.knowledge[g.key] === i ? 'on' : ''}" data-know="${esc(g.key)}" data-v="${i}">${l}</button>`).join('')}</div></div>${sourceTag(src, 'knowledge.' + g.key)}`).join('')}</div>
    <details class="${box} more"><summary><h2>Language and finishing</h2><span class="ms">expand_more</span></summary>
      <div class="knowrow" style="border-top:0"><div style="min-width:0"><h3>English</h3><div class="muted small" data-english-note>${englishNote(p)}</div></div>
        <div class="seg">${['beginner','intermediate','fluent'].map(k => `<button type="button" class="${p.english === k ? 'on' : ''}" data-english="${k}" title="About ${englishWords(k)} common words">${k[0].toUpperCase() + k.slice(1)}</button>`).join('')}</div></div>
      ${p.vocabSize ? `<div data-vocab-row><div class="knowrow"><div style="min-width:0"><h3>Vocabulary size</h3><div class="muted small">About ${p.vocabSize.toLocaleString()} words, set for this person, used instead of the English level</div></div>
        <md-text-button data-vocab-clear>Use English level</md-text-button></div>${sourceTag(src, 'vocabSize')}</div>` : ''}
      <h3 style="margin-top:12px">How they make sure it is done</h3>
      <div class="chips" style="margin-top:8px">${WAYS.map(([k, l]) => `<md-filter-chip label="${l}" data-way="${k}" ${p.confirmBy.includes(k) ? 'selected' : ''}></md-filter-chip>`).join('')}</div>${sourceTag(src, 'confirmBy')}
      ${choiceRow('If no confirmation appears', '', 'ifConfirmMissing', [['let_go', 'Let it go'], ['check', 'Check'], ['redo', 'Do it again']], p.ifConfirmMissing, src)}</details>`;
}
/* A setting with a few named choices. path: a top-level setting or humanFactors.<key>. */
function choiceRow(title, note, path, options, current, src) {
  return `<div class="knowrow"><div style="min-width:0"><h3>${esc(title)}</h3>${note ? `<div class="muted small">${esc(note)}</div>` : ''}</div>
    <div class="seg" role="radiogroup" aria-label="${esc(title)}">${options.map(([v, l]) =>
      `<button type="button" role="radio" aria-checked="${current === v}" class="${current === v ? 'on' : ''}" data-param="${esc(path)}" data-v="${esc(v)}">${esc(l)}</button>`).join('')}</div></div>${sourceTag(src, path)}`;
}
/* How many common words an English level knows: config.toml [words] top_n. */
function englishWords(level) {
  const n = ((window.SUE_PERSONA || {}).english_words || {})[level];
  return n ? n.toLocaleString() : '?';
}
function englishNote(p) { return p.vocabSize ? 'Word knowledge comes from the vocabulary size below' : `Knows the ${englishWords(p.english)} most common words`; }
/* A human factor as it takes effect: unspecified means a typical person (config.toml [persona] typical). */
function factor(p, key) {
  const v = (p.humanFactors || {})[key];
  return !v || v === 'unspecified' ? PersonaParameters.typical()[key] : v;
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
/* The window a participant used longest: a card run from here gets the page they saw (sue.participant reads it the same way). */
function longestWindow(doc) {
  const rows = (doc.events || []).filter(e => e.clientTs), held = new Map();
  let size = null, since = 0;
  rows.forEach((e, i) => {
    const at = Date.parse(e.clientTs), p = e.payload || {};
    const next = e.type === 'session_started' ? p.viewport : e.type === 'viewport_changed' ? p : null;
    if (size && (next || i === rows.length - 1)) held.set(size, (held.get(size) || 0) + at - since);
    if (next) { size = `${next.width}x${next.height}`; since = at; }
  });
  const best = [...held].sort((a, b) => b[1] - a[1])[0];
  if (!best) return (doc.session || {}).viewport || null;
  const [width, height] = best[0].split('x').map(Number);
  return {width, height};
}

function readInput(text) {
  try {
    const doc = JSON.parse(text);
    if (doc && doc.kind === 'sue-questionnaire' && doc.answers) return {kind: 'answers', doc};
    if (doc && doc.kind === 'uat-participant-file') {
      if (!doc.questionnaire || !doc.questionnaire.answers) throw Error('This participant file has no questionnaire answers; the persona is built from them.');
      return {kind: 'answers', doc: doc.questionnaire, postTask: doc.postTask || null, window: longestWindow(doc)};
    }
    if (doc && typeof (doc.transcript || doc.text) === 'string') return {kind: 'survey', text: doc.transcript || doc.text};
  } catch (e) { if (!(e instanceof SyntaxError)) throw e; /* not JSON */ }
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
    let input;
    try { input = readInput(text); }
    catch (e) { $('#draft-area').innerHTML = `<div class="banner bad" style="margin-top:24px"><span class="ms">error</span><div>${esc(e.message)}</div></div>`; return; }
    btn.disabled = true;
    try {
      if (input.kind === 'answers') return fromAnswers(input.doc, input.postTask, input.window);
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
      p.vocabSize = null;  // a description never measures vocabulary; the English level decides
      draft = {kind: 'description', p, description: text};
      renderReview();
    } catch (e) { $('#draft-area').innerHTML = `<div class="banner bad" style="margin-top:24px"><span class="ms">error</span><div>${esc(e.message)}</div></div>`; }
    finally { btn.disabled = false; }
  }
}

/* A participant's own questionnaire answers: the Persona Builder builds the card exactly, no AI. */
function fromAnswers(doc, postTask, seenWindow) {
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
  draft = {kind: 'answers', doc, card, postTask: postTask || null, window: seenWindow || null};
  const during = postTask ? PersonaParameters.fromAnswers(paramsFromCard(card, 'P'), doc.answers, postTask) : null;
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
      ${during ? `<div class="card"><h2>During the task</h2><p class="muted small" style="margin:6px 0 12px">From what they said after the task, 1 to 5, as 0 to 10.</p>
        ${STATES.map(s => `<div class="knowrow"><h3>${s.title}</h3><span>${during[s.key]}</span></div>`).join('')}</div>` : ''}
    </div>
    <div class="card summary">
      <div class="row">${avatar({id: 'draft', name: codeOf(doc.answers.name) || 'P'}, 56)}<div style="min-width:0;flex:1">
        <md-outlined-text-field id="p-name" label="Code name" value="${esc(codeOf(doc.answers.name))}" placeholder="P4" style="width:100%" supporting-text="Only a code name is kept, never their name."></md-outlined-text-field></div></div>
      <div class="chips" style="margin-top:12px">${chipsFor({...scores, fatigue: during ? during.fatigue : 0, distraction: during ? during.distraction : 0, timePressure: during ? during.timePressure : 0}, items.length ? knows / items.length : 0)}</div>
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
  const w = currentWf() || {}, ready = w.status && ['ready', 'changed'].includes(w.status.key);
  const pick = p => `<label class="pick"><md-checkbox touch-target="wrapper" data-pick="${esc(p.id)}" ${p.kind !== 'self' && (!preselect || preselect === p.id) ? 'checked' : ''}></md-checkbox>${avatar(p, 40)}<div style="flex:1;min-width:0"><div>${esc(p.name)}</div><div class="muted small">${kindLabel(p)}</div></div></label>`;
  return `<div class="page">
    <div class="page-head"><div><h1>Run a test</h1><p class="muted">Each persona runs several times, so you see how often a problem happens.</p></div></div>
    ${ready ? '' : `<div class="banner bad"><span class="ms">block</span><div>${esc(w.name || 'This workflow')} is not ready to test. <a href="#test/${esc(w.id)}">Finish setting it up</a> first.</div></div>`}
    <div class="run-grid">
      <div class="stack">
        <div class="card"><div class="row" style="justify-content:space-between"><div style="min-width:0"><h3>${esc(w.name || 'Workflow')}</h3><p class="muted small" style="margin:4px 0 0">${esc(String(w.task || '').split(/(?<=[.!?])\s/)[0])}</p></div></div></div>
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
  const ready = (currentWf() || {}).status && ['ready', 'changed'].includes(currentWf().status.key);
  const chosen = () => $$('[data-pick]').filter(c => c.checked).map(c => c.dataset.pick);
  const summary = () => {
    const n = chosen().length;
    $('#run-summary').innerHTML = n ? `${n} persona${n > 1 ? 's' : ''} × ${runs} runs = <b>${n * runs} runs</b>, about ${n * runs * 3} minutes.` : 'Choose at least one persona.';
    $('#start-run').disabled = !n || !ready || !!S.runJob;
  };
  $('#runs-minus').addEventListener('click', () => { runs = Math.max(1, runs - 1); $('#runs-n').textContent = runs; summary(); });
  $('#runs-plus').addEventListener('click', () => { runs = Math.min(10, runs + 1); $('#runs-n').textContent = runs; summary(); });
  $$('[data-pick]').forEach(c => c.addEventListener('change', summary));
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
      <div class="dots" data-dots="${esc(c)}">${Array.from({length: job.runs}, () => '<span></span>').join('')}</div></div><span></span></div>`).join('')}</div>
    <div class="card" style="margin-top:16px"><div class="row" style="justify-content:space-between;flex-wrap:wrap"><h2 id="live-title">Watching the run</h2><span class="muted small" id="live-phase"></span></div>
      <div class="live inline">
        <div><div class="livescreen" id="live-screen">
          <img id="live-img" alt="What the persona sees now" hidden>
          <div class="lfocus" id="live-focus" hidden></div>
          <svg class="lpointer" id="live-pointer" viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M4 2l15 11-6.5 1.2 3.8 7.3-2.6 1.4-3.8-7.3L4 20z" fill="#e37400" stroke="#fff" stroke-width="1.5"/></svg>
          <div class="lripple" id="live-ripple"></div>
          <div class="lwait" id="live-wait"><md-circular-progress indeterminate></md-circular-progress></div>
        </div></div>
        <div class="log" id="live-log"><div class="muted">Waiting for the first step…</div></div>
      </div></div>`;
  $('#stop-run').addEventListener('click', async () => { try { await api('/api/jobs/stop', {id: job.id}); } catch (e) { fail(e); } });
  pollRun();
  startLive();
}
/* One step as a person would tell it: what they did and how good it looked, where they were looking and how they read the task, why. */
function stepLine(s) {
  const worth = s.worth ? (s.settled ? `took the best, ${s.worth}` : `${s.worth} of ${s.want || '?'}`) : '';
  const reading = (s.reading || '').match(/\$[\d,]*\d/g);
  const where = [s.looking ? `looking at ${s.looking.replace(/ \(piece.*\)/, '')}` : '', reading ? `reads the amount as ${reading[0]}` : ''].filter(Boolean).join(' · ');
  return `<div class="step-line"><span class="n">${s.step}</span><div class="title">${esc(s.did || 'looked around')}</div>${worth ? `<span class="worth ${s.settled ? 'low' : ''}">${esc(worth)}</span>` : '<span></span>'}
    ${where ? `<div class="sub">${esc(where)}</div>` : ''}${s.why ? `<div class="sub why">${esc(s.why)}</div>` : ''}</div>`;
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
  const ph = $('#live-phase'); if (ph) ph.textContent = String(st.phase || '').replace(/^Step \d+: /, '').split(';')[0].slice(0, 80);
}
async function startLive() {
  const job = S.runJob; if (!job) return;
  LIVE.frame = -1; LIVE.dir = null; LIVE.on = true;
  const tick = async () => {
    if (!LIVE.on || !S.runJob || !$('#live-screen')) { LIVE.on = false; return; }
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
      $('#live-log').innerHTML = (v.steps || []).slice().reverse().map(stepLine).join('') || '<div class="muted">Waiting for the first step…</div>';
    } catch (e) { /* between runs */ }
    liveTimer = setTimeout(tick, 300);
  };
  tick();
}
/* ---- results ---- */
pages.results = async () => {
  await loadResults();
  if (!S.results.length) return `<div class="page"><div class="page-head"><div><h1>Results</h1></div></div>
    <div class="card empty"><span class="ms">insights</span><h2>No results for this workflow yet</h2><p class="muted">Run a test and the problems it finds show up here.</p>
    <md-filled-button data-go="run"><span slot="icon" class="ms">play_arrow</span>Run a test</md-filled-button></div></div>`;
  return pages.result(S.results[0].id);
};
/* What happened at a step of the task in one run, as the researcher reads it. */
/* Everything that happened at one step: per run with trouble, the screen they saw, where they
   clicked, what they were thinking, and what should have happened. */
/* ---------------- the result page: three questions, the computation behind every cell (2026-11-01) ---------------- */
const PLAIN = {'Before the form': 'Finding the budget page', Define: 'Naming', Scope: 'Time, project, services', Amount: 'The amount', Actions: 'The alert', 'After the save': 'After the save'};
const KIND = {'lost the way': 'lost the way', 'changed a value': 'changed a value', 'went back': 'went back', 'left unsaved': 'left unsaved', 'wrong when saved': 'saved wrong'};
/* Bars, people beside the engine, drawn to one scale: label, two bars, the two values. */
function barChart(title, rows, fmt, max) {
  const W = 360, L = 150, H = 22, gap = 8, top = 26, right = 48, scale = (W - L - right) / (max || 1);
  const bars = rows.map((r, i) => { const y = top + i * (2 * H + gap);
    return `<text x="${L - 8}" y="${y + H}" text-anchor="end" class="lbl">${esc(r.label)}</text>
      <rect x="${L}" y="${y}" width="${Math.max(1, r.a * scale)}" height="${H - 4}" rx="3" class="p"></rect><text x="${L + r.a * scale + 6}" y="${y + H - 7}" class="val">${esc(fmt(r.a))}</text>
      <rect x="${L}" y="${y + H}" width="${Math.max(1, r.b * scale)}" height="${H - 4}" rx="3" class="e"></rect><text x="${L + r.b * scale + 6}" y="${y + 2 * H - 7}" class="val">${esc(fmt(r.b))}</text>`; }).join('');
  const height = top + rows.length * (2 * H + gap);
  return `<figure class="chart"><figcaption>${esc(title)}</figcaption><svg viewBox="0 0 ${W} ${height}" role="img" aria-label="${esc(title)}"><text x="${L}" y="14" class="legend"><tspan class="lp">■</tspan> people <tspan class="le">■</tspan> engine</text>${bars}</svg></figure>`;
}
function glanceHTML(T) {
  const P = T.people, R = T.runs, parts = T.parts;
  const name = p => (PLAIN[p] || p).replace('Finding the budget page', 'Finding the page');
  const share = (xs, f) => xs.length ? xs.reduce((s, x) => s + f(x), 0) / xs.length : 0;
  const total = x => Object.values(x.seconds).reduce((a, b) => a + b, 0) || 1;
  const trouble = parts.filter(p => p !== 'After the save').map(p => ({label: name(p), a: share(P, x => x.trouble.some(t => t[0] === p) ? 1 : 0), b: share(R, x => x.trouble.some(t => t[0] === p) ? 1 : 0)}));
  const time = parts.map(p => ({label: name(p), a: share(P, x => (x.seconds[p] || 0) / total(x)), b: share(R, x => (x.seconds[p] || 0) / total(x))}));
  const moves = parts.map(p => ({label: name(p), a: share(P, x => x.moves[p] || 0), b: share(R, x => x.moves[p] || 0)}));
  const pct = v => `${Math.round(v * 100)}%`;
  const done = {a: share(P, x => x.passed ? 1 : 0), b: share(R, x => x.passed ? 1 : 0)};
  return `<div class="card"><h2>At a glance</h2><p class="muted small" style="margin:4px 0 12px">${P.length ? `${P.length} people who did the task, beside ${R.length} engine runs.` : `${R.length} engine runs; no participant files for these personas, so the engine stands alone.`}</p>
    <div class="charts">${barChart('Share who had trouble, by part', trouble, pct, 1)}${barChart('Share of the session\'s time, by part', time, pct, Math.max(0.01, ...time.flatMap(r => [r.a, r.b])))}${barChart('Moves made, by part (average)', moves, v => `${Math.round(v)}`, Math.max(1, ...moves.flatMap(r => [r.a, r.b])))}
    <figure class="chart big"><figcaption>Did the task right</figcaption><div class="bignums"><div><span class="n p">${P.length ? pct(done.a) : '—'}</span><span class="muted small">people</span></div><div><span class="n e">${pct(done.b)}</span><span class="muted small">engine runs</span></div></div></figure></div></div>`;
}
function cell(text, title, lines, cls = '') {
  // A value with what it was computed from: the definition, then one line per person or run.
  return `<td><span class="cell-v ${cls}" tabindex="0">${text}<span class="pop"><b>${esc(title)}</b>${lines.length ? `<ul>${lines.map(l => `<li>${esc(l)}</li>`).join('')}</ul>` : ''}</span></span></td>`;
}
function tablesHTML(T) {
  const P = T.people, R = T.runs, nP = P.length, nR = R.length, D = T.definitions;
  const who = x => x.n ? `${x.name} run ${x.n}` : x.name;
  const tally = (xs, f) => { const c = new Map(); xs.forEach(x => { const k = f(x) || '(none)'; c.set(k, (c.get(k) || 0) + 1); }); return [...c].sort((a, b) => b[1] - a[1]); };
  const top = (xs, f, n = 3) => tally(xs, f).slice(0, n).map(([k, v]) => `${k.slice(0, 26)} ${v}`).join(', ') || '—';
  const entryOf = x => /Budgets & caps/.test(x.entry) ? 'side menu' : /Budgets & alerts/.test(x.entry) ? 'search' : x.entry ? 'other' : 'never reached';
  const inPart = (x, part) => x.trouble.filter(t => t[0] === part);
  const lost = x => x.trouble.filter(t => t[1] === 'lost the way').length;
  const wentBack = x => x.trouble.some(t => t[1] === 'went back');
  const head = `<tr><th>What</th><th>People (${nP})</th><th>Engine (${nR} runs)</th></tr>`;
  const row = (what, pf, rf, title, pl, rl, cls) => `<tr><th scope="row">${esc(what)}</th>${nP ? cell(pf(P), title, pl(P), cls) : '<td class="muted">no participant files</td>'}${cell(rf(R), title, rl(R), cls)}</tr>`;
  const list = (xs, f) => xs.map(x => `${who(x)}: ${f(x)}`);
  const q1 = [
    row('First click', xs => top(xs, x => x.first), xs => top(xs, x => x.first), 'The first control each one clicked', xs => list(xs, x => x.first || '(none)'), xs => list(xs, x => x.first || '(none)')),
    row('Way into the form', xs => top(xs, entryOf), xs => top(xs, entryOf), 'The control clicked just before + CREATE BUDGET', xs => list(xs, x => `${entryOf(x)} (${x.entry || '—'})`), xs => list(xs, x => `${entryOf(x)} (${x.entry || '—'})`)),
    row('Went back inside the form', xs => `${xs.filter(wentBack).length} of ${xs.length}`, xs => `${xs.filter(wentBack).length} of ${xs.length}`, D['went back'],
        xs => list(xs.filter(wentBack), x => x.trouble.filter(t => t[1] === 'went back').map(t => t[2]).join('; ')), xs => list(xs.filter(wentBack), x => x.trouble.filter(t => t[1] === 'went back').map(t => t[2]).join('; '))),
  ].join('');
  const troubleRow = part => {
    const f = xs => `${xs.filter(x => inPart(x, part).length).length} of ${xs.length}`;
    const detail = xs => xs.filter(x => inPart(x, part).length).map(x => `${who(x)}: ${part === 'Before the form' ? `${lost(x)} wrong clicks (${[...new Set(inPart(x, part).map(t => t[2]))].slice(0, 6).join(', ')})` : [...new Set(inPart(x, part).map(t => `${KIND[t[1]]}: ${t[2]}`))].join('; ')}`);
    const kinds = part === 'Before the form' ? D['lost the way'] : ['changed a value', 'went back', 'left unsaved', 'wrong when saved'].map(k => `${KIND[k]}: ${D[k]}`).join(' · ');
    return row(PLAIN[part] || part, f, f, `Trouble here means: ${kinds}`, detail, detail);
  };
  const q2 = T.parts.filter(p => p !== 'After the save').map(troubleRow).join('');
  const timeRow = part => {
    const share = xs => xs.length ? `${Math.round(100 * xs.reduce((s, x) => s + (x.seconds[part] || 0) / (Object.values(x.seconds).reduce((a, b) => a + b, 0) || 1), 0) / xs.length)}%` : '—';
    const detail = xs => list(xs, x => `${Math.round(x.seconds[part] || 0)} s of ${Math.round(Object.values(x.seconds).reduce((a, b) => a + b, 0))} s`);
    return row(PLAIN[part] || part, share, share, `Share of the session's time spent here, averaged over sessions. ${D.seconds}`, detail, detail);
  };
  const q2t = T.parts.map(timeRow).join('');
  const amountOf = x => x.saved && x.saved.amount ? `$${x.saved.amount}` : 'nothing saved';
  const failWhy = x => Object.entries(x.checks || {}).filter(([, ok]) => !ok).map(([k]) => k.split(' (')[0]).join('; ');
  const q3 = [
    row('Did the task right', xs => `${xs.filter(x => x.passed).length} of ${xs.length}`, xs => `${xs.filter(x => x.passed).length} of ${xs.length}`, 'Every check passes and they said they were done',
        xs => list(xs, x => x.passed ? 'yes' : `no: ${failWhy(x) || x.stop || 'did not finish'}`), xs => list(xs, x => x.passed ? 'yes' : `no: ${failWhy(x) || x.stop || 'did not finish'}`)),
    row('Amount saved', xs => top(xs, amountOf), xs => top(xs, amountOf), 'The amount in the budget saved last', xs => list(xs, x => `${amountOf(x)}; rules ${(x.saved || {}).rules ? x.saved.rules.join(', ') : '—'}`), xs => list(xs, x => `${amountOf(x)}; rules ${(x.saved || {}).rules ? x.saved.rules.join(', ') : '—'}`)),
  ].join('');
  const byName = new Map(P.map(p => [p.name, p]));
  const personTables = [...new Set(R.map(r => r.name))].map(name => {
    const rs = R.filter(r => r.name === name), p = byName.get(name);
    const seq = f => rs.map(f).join(', ');
    const inForm = x => T.parts.slice(1, -1).reduce((s, k) => s + (x.moves[k] || 0), 0);
    const ft = x => [...new Set(x.trouble.filter(t => t[1] !== 'lost the way').map(t => `${PLAIN[t[0]] || t[0]}: ${KIND[t[1]]}`))].join('; ') || 'none';
    const rows = [['Did the task right', p ? (p.passed ? 'yes' : 'no') : '—', seq(r => r.passed ? 'yes' : 'no')], ['First click', p ? p.first : '—', seq(r => r.first)],
      ['Wrong clicks before the form', p ? lost(p) : '—', seq(lost)], ['Moves inside the form', p ? inForm(p) : '—', seq(inForm)],
      ['Amount saved', p ? amountOf(p) : '—', seq(amountOf)], ['Trouble inside the form', p ? ft(p) : '—', rs.map((r, i) => `run ${i + 1}: ${ft(r)}`).join('<br>')]];
    return `<div class="card"><div class="row" style="gap:12px;margin-bottom:8px">${avatar({id: rs[0].card, name}, 36)}<h3>${esc(name)}</h3>${p ? '' : '<span class="muted small">no participant file</span>'}</div>
      <table class="matrix q"><tr><th></th><th>Person</th><th>Engine, ${rs.length} run${rs.length > 1 ? 's' : ''}</th></tr>${rows.map(([a, b, c]) => `<tr><th scope="row">${a}</th><td>${a.startsWith('Trouble') ? b : esc(String(b))}</td><td>${a.startsWith('Trouble') ? c : esc(String(c))}</td></tr>`).join('')}</table>
      <p class="muted small" style="margin:8px 0 0">${rs.map((r, i) => `<a href="${r.report}" target="_blank">run ${i + 1}</a>`).join(' · ')}</p></div>`;
  }).join('');
  return `${glanceHTML(T)}<div class="card"><h2>Is the direction right?</h2><table class="matrix q">${head}${q1}</table></div>
    <div class="card"><h2>Where does it go wrong?</h2><p class="muted small" style="margin:4px 0 10px">How many had trouble in each part. Hover a number for who, and what.</p><table class="matrix q">${head}${q2}</table>
      <h3 style="margin-top:20px">Where does the time go?</h3><table class="matrix q">${head}${q2t}</table></div>
    <div class="card"><h2>Is the task done?</h2><table class="matrix q">${head}${q3}</table></div>
    <h2 style="margin:24px 0 12px">Each persona</h2>${personTables}`;
}
pages.result = async (id) => {
  const [T] = await Promise.all([api(`/api/tables?id=${encodeURIComponent(id)}`), loadResults()]);
  const others = (S.results || []).map(r => `<md-filter-chip label="${esc(when(r.at))} · ${r.runs} run${r.runs === 1 ? '' : 's'}" data-go="result/${esc(r.id)}" ${r.id === id ? 'selected' : ''}></md-filter-chip>`).join('');
  return `<div class="page">
    <div class="page-head"><div><h1>Result · ${esc(when(T.at))}</h1><p class="muted">${T.runs.length} runs of ${new Set(T.runs.map(r => r.card)).size} personas${T.people.length ? `, read against ${T.people.length} participant${T.people.length > 1 ? 's' : ''} who did the task` : ''}. Hover any number for how it was computed.</p></div>
    </div>
    ${others ? `<div class="chips" style="margin:0 0 16px">${others}</div>` : ''}
    ${tablesHTML(T)}</div>`;
};

/* ---------------- router ---------------- */
function go(name) { location.hash = name; }
let rendering = 0;
async function render() {
  const n = ++rendering;
  let [name, arg] = (location.hash || '#workflow').slice(1).split('/');
  name = {home: 'workflow', tests: 'workflow', workflows: 'workflow', 'new-test': 'workflow', test: 'workflow', 'new-workflow': 'workflow'}[name] || name;  // one workflow: those pages are gone
  const page = pages[name] ? name : 'workflow';
  try {
    const html = await pages[page](arg && decodeURIComponent(arg));
    if (n !== rendering) return;
    $('#main').innerHTML = html;
  } catch (e) { $('#main').innerHTML = `<div class="page"><div class="banner bad" style="margin-top:24px"><span class="ms">error</span><div>${esc(e.message)}</div></div></div>`; return; }
  const nav = {new: 'personas', result: 'results'}[page] || page;
  $$('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === nav));
  if (page === 'new') setupComposer();
  if (page === 'run') setupRun();
}

/* ---------------- events ---------------- */
document.addEventListener('click', async e => {
  const t = e.target.closest('[data-param],[data-vocab-clear],[data-go],[data-open],[data-remove],[data-know],[data-english],#rail-fab,#scrim,#sheet-close,#sheet-cancel,#sheet-save,#sheet-dup,#sheet-run,#discard-keep,#discard-yes,#create,#create-run,#help-btn');
  if (!t) return;
  try {
    if (t.matches('[data-remove]')) {
      e.stopPropagation();
      const p = S.personas.find(x => x.id === t.dataset.remove);
      await api('/api/personas/delete', {id: p.id}); await render();
      snack(`Deleted “${p.name}”`, async () => { await api('/api/personas/restore', {id: p.id}); render(); });
      return;
    }
    if (t.matches('[data-go]')) return go(t.dataset.go);
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
    if (t.matches('#help-btn')) return snack('Personas run the workflow; watch a run on the Run page; the results read each run against the people who did the task.');
    if (t.matches('[data-know]')) {
      const p = editing(t); if (!p) return;
      PersonaParameters.setGroup(p, t.dataset.know, Number(t.dataset.v));
      t.parentElement.querySelectorAll('button').forEach(b => { const on = b === t; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); });
      return refreshChips(t);
    }
    if (t.matches('[data-param]')) {
      const p = editing(t); if (!p) return;
      const [a, b] = t.dataset.param.split('.');
      if (b) p[a][b] = t.dataset.v; else p[a] = t.dataset.v;
      t.parentElement.querySelectorAll('button').forEach(x => { x.classList.toggle('on', x === t); x.setAttribute('aria-checked', String(x === t)); });
      return refreshChips(t);
    }
    if (t.matches('[data-english]')) { const p = editing(t); if (!p) return; p.english = t.dataset.english; t.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === t));
      t.closest('[data-editor]').querySelector('[data-english-note]').textContent = englishNote(p); return refreshChips(t); }
    if (t.matches('[data-vocab-clear]')) { const p = editing(t); if (!p) return; p.vocabSize = null; const root = t.closest('[data-editor]');
      root.querySelector('[data-english-note]').textContent = englishNote(p); t.closest('[data-vocab-row]').remove(); return refreshChips(root); }
    if (t.matches('#create,#create-run')) {
      const typed = ($('#p-name').value || '').trim();
      if (draft.kind !== 'description' && !/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(typed)) return snack('Give the participant a code name, such as P4. Their name is never kept.');
      let r, made;
      if (draft.kind === 'answers') {
        const parameters = PersonaParameters.fromAnswers(paramsFromCard(draft.card, typed), draft.doc.answers, draft.postTask);
        r = await api('/api/personas/save-participant', {code: typed, card: draft.card, answers: draft.doc, parameters, postTask: draft.postTask, window: draft.window,
          built: draft.postTask ? buildBundle(parameters).card : undefined});
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
  } catch (err) { fail(err); }
});
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
});
document.addEventListener('click', e => {
  const chip = e.target.closest && e.target.closest('md-filter-chip[data-way]');
  if (chip) setTimeout(() => { const p = editing(chip); if (!p) return; const on = $$('[data-editor] md-filter-chip[data-way]').filter(c => c.closest('[data-editor]') === chip.closest('[data-editor]') && c.selected).map(c => c.dataset.way);
    if (!on.length) { chip.selected = true; return snack('Keep at least one way of making sure.'); } p.confirmBy = on; refreshChips(chip); });
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && sheetFor && !$('#discard-dialog').open) tryClose(); });
window.addEventListener('hashchange', render);
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
