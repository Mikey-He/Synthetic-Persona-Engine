/* Direct-profile editor. Reuses the original builder for scaffold and behavior levels. */
'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const HIDDEN_KNOWLEDGE=new Set(['navigation','operations','icons']);
const VISIBLE_KNOWLEDGE=PersonaParameters.GROUPS.filter(g=>!HIDDEN_KNOWLEDGE.has(g.key));
const VISIBLE_HUMAN_FACTORS=PersonaParameters.HUMAN_FACTORS.filter(f=>f.key!=='searchPreference');
const LEVELS = ['Low', 'Medium', 'High'];
const FIELDS = [
  {key:'risk', title:'Risk tolerance', code:'risk', descriptions:[
    'Looks for understood evidence. Avoids uncertain clicks and may go back or give up.',
    'Looks for help and reads on before trying a partly understood or similar option.',
    'Tries partly understood options; explores a similar-looking option sooner.'
  ]},
  {key:'patience', title:'Patience', code:'patience', descriptions:[
    'A small wrong-turn budget: the current engine uses a threshold of 3 wrong turns plus backtracks.',
    'A moderate wrong-turn budget: the current engine uses a threshold of 6.',
    'A larger wrong-turn budget: the current engine uses a threshold of 10.'
  ]},
  {key:'detailFind', title:'Detail when finding', code:'detailFind', descriptions:[
    'Reads one small piece at a time, such as a menu group. Low and medium currently share this rule.',
    'Reads one small piece at a time, such as a menu group. Low and medium currently share this rule.',
    'Takes in a whole region at once, increasing the set of visible candidates.'
  ]},
  {key:'detailCheck', title:'Detail when checking', code:'detailCheck', descriptions:[
    'Focuses on what the task explicitly asks. May miss default values that also need changing.',
    'Checks values against the task; avoids experimenting with unclear options.',
    'Checks each field and may try unclear options. Can reopen a saved item when list confirmation and the required knowledge are present.'
  ]}
];
// States during the task (engine-design.md 4.9): 0 means no effect.
const STATE_FIELDS = [
  {key:'fatigue', title:'Fatigue', code:'fatigue', note:'Carefulness and patience fall as the task goes on and reading builds up.'},
  {key:'distraction', title:'Distraction / multitasking', code:'distraction', note:'Each piece of screen read carries a chance of missing one of its less prominent elements.'},
  {key:'timePressure', title:'Time pressure', code:'timePressure', note:'Reads less, takes more risk and gives up sooner. How it changes is set under Pressure over the task below.'}
];
const SCORES = [0,2.5,5,7.5,10];
// What a score does each step: 0 always low, 5 always medium, 10 always high, in between a mix.
function mix(score) {
  if (score <= 5) { const m = Math.round(score / 5 * 100); return m === 0 ? 'Always low' : m === 100 ? 'Always medium' : `Low ${100 - m}% · medium ${m}% of steps`; }
  const h = Math.round((score - 5) / 5 * 100); return h === 100 ? 'Always high' : `Medium ${100 - h}% · high ${h}% of steps`;
}
const WAYS = [
  ['action','Last button clicked','No additional confirmation'],
  ['list','Check the saved list','Available in this prototype'],
  ['toast','Success message','Not provided by this prototype'],
  ['external','Email or notification','Not provided by this prototype'],
  ['test','Make the alert trigger','Not provided by this prototype']
];
const RESULT_LABELS = {understands:'Understands', vague:'Vague', everyday:'Everyday only', none:'Unknown', other:'Other meaning', misleads:'Misleading habit', may_mislead:'Possible misleading habit', unaffected:'Unaffected'};
let parameters = PersonaParameters.defaults();
let builder, flow, bundle, runtime, token, jobId, pollTimer, busy = false;
let extraction = null, extracting = false;
let vocabularyPreview=null, wordTimer, wordVersion=0, wordSignature='';
const STORAGE = 'sue-persona-studio-v3';  // v2 drafts held levels 0-2, not scores
try { const stored = localStorage.getItem(STORAGE); if (stored) parameters = PersonaParameters.validate(JSON.parse(stored)); } catch (_) { /* Ignore an invalid or unavailable draft. */ }

function persist() { try {localStorage.setItem(STORAGE, JSON.stringify(parameters));} catch (_) {} }
function status(text) { $('save-state').textContent = text; }
function showError(error) { status(error.message || String(error)); }
function controls() {
  $('name').value = parameters.name;
  $('english').value = parameters.english;
  $('vocab').value = parameters.vocabSize ?? '';
  $('missing').value = parameters.ifConfirmMissing;
  const slider = (f, extra) => `<div class="control"><div class="control-heading"><h3>${f.title}</h3><small>${f.code}</small></div><div class="score-row"><input type="range" min="0" max="10" step="0.5" value="${parameters[f.key]}" data-score="${f.key}" aria-label="${f.title}, score 0 to 10"><output>${parameters[f.key]}</output></div>${extra}</div>`;
  $('behaviors').innerHTML = FIELDS.map(f => slider(f, `<p class="score-mix">${mix(parameters[f.key])}</p><p>${f.descriptions[PersonaParameters.nearest(parameters[f.key])]}</p>`)).join('')
    + `<h3 class="states-heading">During the task</h3>` + STATE_FIELDS.map(f => slider(f, `<p>${parameters[f.key] === 0 ? 'Off. ' : ''}${f.note}</p>`)).join('');
  $('completion').innerHTML = WAYS.map(([value, label, note]) => `<label class="check-choice"><input type="checkbox" value="${value}" ${parameters.confirmBy.includes(value)?'checked':''}><span>${label}<small>${note}</small></span></label>`).join('');
  renderHumanFactors();
  renderKnowledgeControls();
  renderVocabulary();
}
function renderHumanFactors(){
  const groups=[...new Set(VISIBLE_HUMAN_FACTORS.map(f=>f.group))];
  $('human-factor-controls').innerHTML=groups.map(group=>`<div class="factor-group"><h3>${group}</h3><div class="knowledge-grid">${VISIBLE_HUMAN_FACTORS.filter(f=>f.group===group).map(f=>`<label class="field">${f.title} <small class="${PersonaParameters.ENGINE_FACTORS.includes(f.key)?'factor-on':'factor-off'}">${PersonaParameters.ENGINE_FACTORS.includes(f.key)?'Affects the engine':'Recorded only'}</small><select data-human-factor="${f.key}">${f.choices.map(([value,label])=>`<option value="${value}" ${parameters.humanFactors[f.key]===value?'selected':''}>${label}</option>`).join('')}</select><small>${f.help}</small></label>`).join('')}</div></div>`).join('');
}
$('human-factor-controls').onchange=event=>{const key=event.target.dataset.humanFactor;if(!key)return;parameters.humanFactors[key]=event.target.value;update();renderBatchBaselines();};
function renderKnowledgeControls() {
  $('knowledge-controls').innerHTML=VISIBLE_KNOWLEDGE.map(g=>{
    const choices=g.word?['Unknown','Everyday meaning','Technical understanding']:['Unknown','Vaguely known','Understood'];
    return `<div class="knowledge-control" id="knowledge-${g.key}"><h3>${g.title}</h3><select data-knowledge="${g.key}" aria-label="${g.title}">${choices.map((v,i)=>`<option value="${i}" ${parameters.knowledge[g.key]===i?'selected':''}>${v}</option>`).join('')}</select><p>${g.examples}</p></div>`;
  }).join('');
}
function renderVocabulary() {
  $('english').disabled=false;
  $('vocab-presets').innerHTML=`<button type="button" data-vocabulary="auto" aria-pressed="${parameters.vocabSize===null}">Auto</button>`+[2000,5000,10000,20000,30000,40000].map(n=>`<button type="button" data-vocabulary="${n}" aria-pressed="${parameters.vocabSize===n}">${(n/1000)}k</button>`).join('');
  const fallback={beginner:500,intermediate:2000,fluent:20000};
  $('vocab-summary').textContent=parameters.vocabSize===null?`Using the current engine's ${parameters.english} fallback: ${fallback[parameters.english].toLocaleString()} words.`:`Estimated ${parameters.vocabSize.toLocaleString()} words. This is a manual scenario setting, not a measured test score.`;
}
function profileMessage(text,error=false) {
  $('profile-message').textContent=text;
  $('profile-message').className='note '+(error?'error-text':'success-text');
}
function renderWordRows() {
  if(!vocabularyPreview)return;
  const category=$('word-category').value, visibility=$('word-visibility').value, query=$('word-search').value.toLowerCase().trim();
  const rows=vocabularyPreview.rows.filter(row=>row.category===category && (!query || row.text.toLowerCase().includes(query)));
  const shown=rows.filter(row=>visibility==='all' || row.readable===(visibility==='readable'));
  $('word-counts').textContent=`${rows.filter(r=>r.readable).length} readable · ${rows.filter(r=>!r.readable).length} replaced · showing ${shown.length}`;
  $('word-rows').innerHTML=shown.map(row=>`<tr><td>${escapeHTML(row.text)}</td><td><span class="${row.readable?'word-readable':'word-replaced'}">${row.readable?'Readable':'Replaced'}</span><small>${escapeHTML(row.states.join(', '))}</small></td><td>${escapeHTML(row.shown)}</td><td>${escapeHTML(row.reason)}${row.rank?' Rank: '+row.rank.toLocaleString():''}</td></tr>`).join('') || '<tr><td colspan="4">No matching words in this reference list.</td></tr>';
}
function scheduleWordPreview(force=false) {
  if(!token || !bundle)return;
  const card=bundle.card, extra=$('word-extra-text').value;
  const signature=JSON.stringify({language:card.persona.lang,type:card.persona.cardType,words:card.screens.map(s=>s.words),extra});
  if(!force && signature===wordSignature)return;
  wordSignature=signature;const version=++wordVersion;
  clearTimeout(wordTimer);vocabularyPreview=null;
  renderPreview(card);
  $('word-rows').innerHTML='';$('word-counts').textContent='';
  $('vocabulary-preview-status').textContent='Updating word visibility using the original engine…';
  wordTimer=setTimeout(async()=>{
    try{
      const result=await request('/api/vocabulary-preview',{card,text:extra});
      if(version!==wordVersion)return;
      vocabularyPreview=result;
      if(bundle)renderPreview(bundle.card);
      $('vocabulary-preview-status').textContent=`Vocabulary threshold: ${result.limit.toLocaleString()} words. Original reference sample: ${result.sampleReadable}/${result.sampleTotal} estimated readable. Expand to inspect.`;
      $('vocabulary-method').textContent=result.scope+' '+result.method;
      $('word-example').textContent='Original: '+result.example.original+'\nEngine sees: '+result.example.shown;
      renderWordRows();
    }catch(error){
      if(version!==wordVersion)return;
      wordSignature='';$('vocabulary-preview-status').textContent='Word preview unavailable: '+error.message+'. The card has not been changed.';
    }
  },200);
}
for(const id of ['word-category','word-visibility']) $(id).addEventListener('change',renderWordRows);
$('word-search').addEventListener('input',renderWordRows);
$('refresh-words').onclick=()=>scheduleWordPreview(true);
function renderPreview(card) {
  const section=(number,title,target,contents)=>`<section class="preview-group"><h3><a href="#${target}">${number} · ${title} <span>↗</span></a></h3>${contents}</section>`;
  const line=(label,value,attrs='')=>`<div class="preview-setting"><span>${escapeHTML(label)}</span><b ${attrs}>${escapeHTML(value)}</b></div>`;
  $('preview-avatar').textContent=parameters.name.trim().split(/\s+/).slice(0,2).map(word=>word[0]).join('').toUpperCase() || 'P';
  const adjusted=FIELDS.some(f=>card.tendency[f.key].score!==parameters[f.key]);
  $('profile-bars').innerHTML=section('02','Behavior','behavior-section',
    FIELDS.map(f=>{
      const score=card.tendency[f.key].score;
      const changed=score!==parameters[f.key];
      return `<div class="bar-row"><div class="bar-title"><span>${f.title}</span><b data-engine="${f.key}">${score} · ${mix(score)}</b></div><div class="bar-track score" role="img" aria-label="${f.title}: ${score} of 10">${[...Array(10)].map((_,n)=>`<i class="${n<score?'on':''}"></i>`).join('')}</div>${changed?`<p class="bar-adjustment">Your setting: <span data-usual="${f.key}">${parameters[f.key]}</span> → ${score} after high stakes.</p>`:`<span hidden data-usual="${f.key}">${parameters[f.key]}</span>`}</div>`;
    }).join('')+
    STATE_FIELDS.map(f=>line(f.title, f.key==='timePressure'?`${card.state.timePressure.score} · ${card.state.timePressure.pattern.replace(/_/g,' ')}`:String(card.state[f.key]))).join('')+
    `<p class="note">${adjusted?'Scores differ from your settings because high stakes shift them one level.':'Each step the engine draws low, medium or high from these scores.'}</p>`);
  const stateLabels={none:'Unknown',everyday:'Everyday meaning',vague:'Vaguely known',understands:'Understood',other:'Other meaning'};
  $('preview-knowledge').innerHTML=section('03','Knowledge','knowledge-section',VISIBLE_KNOWLEDGE.map(group=>{
    const states=Array.from(new Set(card.items.filter(i=>group.ids.includes(i.id)).map(i=>i.result)));
    const actual=states.length===1?(group.word && states[0]==='understands'?'Technical understanding':stateLabels[states[0]]):'Mixed item settings';
    return line(group.title,actual,`data-knowledge-preview="${group.key}"`);
  }).join(''));
  $('preview-human-factors').innerHTML=section('＋','Additional human factors','human-factors-section','<p class="note">Marked ● affect the engine; the rest are recorded only</p>'+VISIBLE_HUMAN_FACTORS.map(f=>line((PersonaParameters.ENGINE_FACTORS.includes(f.key)?'● ':'')+f.title,f.choices.find(([v])=>v===parameters.humanFactors[f.key])[1])).join(''));
  const fallback=vocabularyPreview?.levelDefaults || {beginner:500,intermediate:2000,fluent:20000};
  const limit=card.persona.lang.vocabSize || fallback[card.persona.lang.english];
  $('preview-language').innerHTML=section('04','Language & vocabulary','language-section',
    line('English level',parameters.english.replace(/^./,c=>c.toUpperCase()),'data-preview="english"')+
    line('Vocabulary',limit.toLocaleString()+' · '+(parameters.vocabSize===null?'Auto':'manual estimate'),'data-preview="vocabulary"')+
    `<p class="note">${vocabularyPreview?`${vocabularyPreview.sampleReadable}/${vocabularyPreview.sampleTotal} reference words estimated readable.`:'Word visibility preview updating…'} <a href="#vocabulary-details" data-open-word-details>Inspect word list ↗</a></p>`);
  const completion=parameters.confirmBy.map(value=>WAYS.find(w=>w[0]===value)?.[1] || value).join('; ');
  const missing={let_go:'Let it go',check:'Go back and check',redo:'Redo the setup'};
  $('preview-completion').innerHTML=section('05','Finish line','completion-section',line('Confirm by',completion,'data-preview="completion"')+line('If missing',missing[parameters.ifConfirmMissing],'data-preview="missing"'));
}
$('preview-language').onclick=event=>{
  if(event.target.closest('[data-open-word-details]'))$('vocabulary-details').open=true;
};
function update() {
  if (!builder) return;
  try {
    bundle = PersonaParameters.build(parameters, builder, flow);
    const card = bundle.card;
    if(document.querySelector('[data-batch-base]'))renderBatchBaselines();
    $('preview-name').textContent = parameters.name;
    renderPreview(card);
    renderVocabulary();
    scheduleWordPreview();
    $('json').textContent = JSON.stringify(card, null, 2);
    const available = parameters.confirmBy.some(w => w === 'action' || card.goal.productSignals[w]);
    $('signal-note').textContent = available ? 'At least one selected completion signal is available in this prototype.' : 'None of the selected signals is available. The engine will use its existing missing-confirmation behavior.';
    $('save').disabled = busy || !token;
    $('download').disabled = false;
    $('run').disabled = busy || Boolean(jobId) || !runtime?.ready;
    persist();
  } catch (error) {
    bundle = null;
    clearTimeout(wordTimer);wordVersion++;wordSignature='';vocabularyPreview=null;
    $('word-rows').innerHTML='';$('vocabulary-preview-status').textContent='Fix the configuration to calculate word visibility.';
    $('save').disabled = $('run').disabled = $('download').disabled = true;
    showError(error);
  }
}
async function request(url, body) {
  const response = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Studio-Token':token}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || `Request failed (${response.status}).`);
  return data;
}
async function refresh() {
  try {
    runtime = await request('/api/status'); token = runtime.token;
    $('extract-survey').disabled = extracting;
    $('runtime-state').textContent = runtime.ready ? 'Ready: Save & Run runs the card 5 times with different seeds.' : 'Card editing works. Engine setup is incomplete.';
    $('runtime-state').className = `note ${runtime.ready?'ready':'blocked'}`;
    $('requirements').innerHTML = runtime.checks.map(c=>`<li class="${c.ok?'ready':'blocked'}">${c.ok?'✓':'○'} ${escapeHTML(c.label)}</li>`).join('');
    if (builder) update();
    if (runtime.activeJob && !jobId) {
      jobId = runtime.activeJob;
      $('run-panel').hidden = false;
      poll();
    }
  } catch (error) { $('runtime-state').textContent = 'Local server unavailable. Restart Open Persona Studio.command.'; showError(error); }
}
async function save(andRun) {
  if (!bundle) return;
  busy = true; update();
  try {
    const snapshot = bundle;
    const result = await request('/api/save', snapshot);
    status(`Saved ${result.filename}. Existing cards were not overwritten.`);
    if (andRun) {
      const started = await request('/api/run', {card:result.id, runs:5});
      jobId = started.id;
      update();
      $('run-panel').hidden = false;
      $('run-panel').scrollIntoView({behavior:'smooth',block:'start'});
      $('report').hidden = true;
      await poll();
    }
  } catch (error) { showError(error); }
  finally {busy = false; update();}
}
async function poll() {
  clearTimeout(pollTimer);
  if (!jobId) return;
  try {
    const job = await request(`/api/job?id=${encodeURIComponent(jobId)}`);
    $('run-state').textContent = job.state === 'running' ? `Running ${job.card} on the platform, 5 seeded runs…` : job.state === 'completed' ? 'Finished. Open the report for what the runs add up to.' : job.state === 'stopped' ? 'Run stopped.' : 'Engine run failed. See output below.';
    $('run-log').textContent = job.log || 'Starting engine…';
    $('stop').hidden = job.state !== 'running';
    if (job.report) { $('report').href = job.report; $('report').hidden = false; }
    if (job.state === 'running') pollTimer = setTimeout(poll, 1500);
    else { jobId = null; await refresh(); }
  } catch (error) { $('run-state').textContent = error.message; pollTimer = setTimeout(poll, 3000); }
}
function download(filename, object) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(object,null,2)+'\n'], {type:'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 2000);
}
$('behaviors').addEventListener('input', event => {
  const key = event.target.dataset.score; if (!key) return;
  parameters[key] = Number(event.target.value);
  event.target.nextElementSibling.textContent = event.target.value;
  update(); status('Updated preview. Save to create a new card.');
});
$('behaviors').addEventListener('change', event => {
  const key = event.target.dataset.score; if (!key) return;
  controls(); $('behaviors').querySelector(`[data-score="${key}"]`).focus();
});
$('knowledge-controls').addEventListener('change',event=>{
  if(!event.target.dataset.knowledge) return;
  PersonaParameters.setGroup(parameters,event.target.dataset.knowledge,Number(event.target.value));
  update();status('Direct knowledge updated. Its item exceptions were cleared.');
});
$('vocab-presets').addEventListener('click',event=>{
  const button=event.target.closest('[data-vocabulary]');if(!button)return;
  parameters.vocabSize=button.dataset.vocabulary==='auto'?null:Number(button.dataset.vocabulary);$('vocab').value=parameters.vocabSize??'';
  update();status('Estimated vocabulary updated. No word-by-word answers are generated.');
});
function proposalDisplay(proposal) {
  const field=[...FIELDS,...STATE_FIELDS].find(f=>f.key===proposal.path);
  if(field)return field.title+' → '+proposal.value+' of 10';
  if(proposal.path.startsWith('knowledge.')) {
    const group=PersonaParameters.GROUPS.find(g=>g.key===proposal.path.slice(10));
    if(group)return group.title+' → '+(group.word?['Unknown','Everyday meaning','Technical understanding']:['Unknown','Vaguely known','Understood'])[proposal.value];
  }
  if(proposal.path.startsWith('humanFactors.')){const f=PersonaParameters.HUMAN_FACTORS.find(f=>'humanFactors.'+f.key===proposal.path);return f.title+' → '+f.choices.find(([v])=>v===proposal.value)[1]+' (configuration only)';}
  const labels={english:'English level',vocabSize:'Estimated vocabulary',confirmBy:'Completion signals',ifConfirmMissing:'Missing confirmation',urgency:'Time pressure',stakes:'Consequences'};
  const values={calm:'Normal',urgent:'Urgent',low:'Low',high:'High',let_go:'Let it go',check:'Check',redo:'Redo'};
  let value=proposal.value;
  if(proposal.path==='confirmBy')value=value.map(v=>WAYS.find(w=>w[0]===v)?.[1] || v).join(', ');
  else if(typeof value==='number')value=value.toLocaleString();
  else value=values[value] || value;
  return (labels[proposal.path] || proposal.path)+' → '+value;
}
function setSurveyText(result) {
  $('profile-text').value=result.text;
  $('extraction-review').hidden=true;extraction=null;
  profileMessage((result.name?result.name+' · ':'')+result.source+' Ready to summarize.');
}
$('upload-interview').onclick=()=>$('interview-file').click();
$('interview-file').onchange=async event=>{
  try{
    const file=event.target.files[0];if(!file)return;
    if(file.size>1000000)throw Error('Choose an interview file under 1 MB.');
    const text=await file.text();
    if(file.name.toLowerCase().endsWith('.json'))setSurveyText(await request('/api/read-interview',{document:JSON.parse(text)}));
    else {
      if(!text.trim() || text.length>30000)throw Error('Use an interview between 1 and 30,000 characters.');
      setSurveyText({text,source:'Interview text loaded. The same extraction template is used for any participant.'});
    }
  }catch(error){profileMessage(error.message,true);}finally{event.target.value='';}
};
$('extract-survey').onclick=async()=>{
  if(extracting)return;
  extracting=true;$('extract-survey').disabled=true;$('extract-survey').textContent='Reading the interview…';
  $('extraction-review').hidden=true;extraction=null;
  profileMessage('Extracting evidence from the original text. Settings have not changed. This can take a minute.');
  try{
    const sourceText=$('profile-text').value;
    extraction=await request('/api/extract-interview',{text:sourceText});
    extraction.sourceText=sourceText;
    $('extraction-summary').textContent=extraction.summary;
    $('extraction-updates').innerHTML=extraction.updates.map((u,i)=>`<label class="extraction-choice"><input type="checkbox" data-proposal="${i}" ${u.confidence==='explicit'?'checked':''}><span><b>${escapeHTML(proposalDisplay(u))}</b><small>${u.confidence==='inferred'?'Tentative interpretation · select only if you agree':'Directly reported'}</small><blockquote>${escapeHTML(u.quote)}</blockquote><small>${escapeHTML(u.reason)}</small></span></label>`).join('') || '<p class="note">No supported parameter changes could be established. The summary is still available.</p>';
    $('extraction-unknowns').textContent='Not established: '+extraction.unknowns.join('; ')+'. Unselected and unknown fields keep the current test settings, which are not newly validated by this text.';
    $('extraction-review').hidden=false;
    profileMessage('Extraction finished. Review evidence and select changes before applying.');
  }catch(error){profileMessage(error.message,true);}finally{extracting=false;$('extract-survey').disabled=!token;$('extract-survey').textContent='Extract persona settings';}
};
$('apply-extraction').onclick=()=>{
  try{
    if(!extraction)throw Error('Extract the text first.');
    if($('profile-text').value!==extraction.sourceText)throw Error('Source text changed. Extract it again before applying.');
    const next=JSON.parse(JSON.stringify(parameters));
    const selected=Array.from($('extraction-updates').querySelectorAll('input:checked'),input=>extraction.updates[Number(input.dataset.proposal)]);
    for(const update of selected){
      if(update.path.startsWith('knowledge.'))PersonaParameters.setGroup(next,update.path.slice(10),update.value);
      else if(update.path.startsWith('humanFactors.'))next.humanFactors[update.path.split('.')[1]]=update.value;
      else next[update.path]=update.value;
    }
    parameters=PersonaParameters.validate(next);controls();update();
    $('extraction-review').hidden=true;
    profileMessage(`Applied ${selected.length} reviewed changes. Other settings remain unchanged.`);
  }catch(error){profileMessage(error.message,true);}
};
$('dismiss-extraction').onclick=()=>{$('extraction-review').hidden=true;extraction=null;profileMessage('Extraction dismissed. No settings changed.');};
$('completion').addEventListener('change', event => {
  const selected = Array.from($('completion').querySelectorAll('input:checked'), el=>el.value);
  if (!selected.length) {event.target.checked = true; status('Keep at least one completion signal.'); return;}
  parameters.confirmBy = selected; update(); status('Completion settings updated. Save to create a new card.');
});
$('name').addEventListener('input', event => {parameters.name = event.target.value; update();});
$('english').addEventListener('change', event => {parameters.english = event.target.value; parameters.vocabSize=null;$('vocab').value='';update();status('English level changed. Using its Auto vocabulary default; a manual count can override it.');});
$('vocab').addEventListener('input', event => {parameters.vocabSize = event.target.value === '' ? null : Number(event.target.value); update();});
$('missing').addEventListener('change', event => {parameters.ifConfirmMissing = event.target.value; update();});
$('save').onclick = ()=>save(false); $('run').onclick = ()=>save(true);
$('refresh').onclick = refresh;
$('stop').onclick = async()=>{try {await request('/api/stop',{id:jobId}); await poll();} catch(error){showError(error);}};
$('download').onclick = ()=>{if(bundle)download('persona-card.json',bundle.card);};
$('export-params').onclick = ()=>{try{download('persona-settings.json',PersonaParameters.settings(parameters));}catch(error){showError(error);}};
$('import-params').onclick = ()=>$('import-file').click();
$('import-file').onchange = async event => {
  try {
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 100000) throw Error('Settings file is too large.');
    parameters = PersonaParameters.fromJSON(await file.text()); controls(); update(); status('Settings imported. Save to create a new card.');
  } catch(error){showError(error);} finally {event.target.value='';}
};
$('reset').onclick = ()=>{parameters=PersonaParameters.defaults(); controls(); update(); status('Restored the starting interview test profile. Saved cards were kept.');};
function connectBuilder() {
  if (builder) return;
  try {
    const frame = $('builder').contentWindow;
    if (!frame.__sueBuilder) return;
    builder = frame.__sueBuilder;
    flow = JSON.parse(frame.document.getElementById('flow').textContent);
    controls(); update(); status('Preview ready. Save creates a new card in data/personas.');
  } catch(error){showError(error);}
}
$('builder').addEventListener('load', connectBuilder);
connectBuilder(); controls(); refresh();

// Batch generation uses the same compiler as the manual editor.
const batchFields=[...FIELDS.map(f=>[f.key,f.title]),...STATE_FIELDS.map(f=>[f.key,f.title]),...VISIBLE_KNOWLEDGE.map(g=>['knowledge.'+g.key,g.title]),['english','English level'],['vocabSize','Vocabulary size'],['confirmBy','Completion signal'],['ifConfirmMissing','Missing confirmation'],...VISIBLE_HUMAN_FACTORS.map(f=>['humanFactors.'+f.key,f.title+' (configuration only)'])];
$('batch-fields').innerHTML=batchFields.map(([key,title])=>`<div class="batch-parameter"><label class="check-choice"><input type="checkbox" data-batch-field="${key}" ${key.startsWith('humanFactors.')?'':'checked'}><span>${escapeHTML(title)}</span></label><label class="batch-base-field">Base setting<select data-batch-base="${key}" aria-label="Base setting: ${escapeHTML(title)}"></select></label></div>`).join('');
const additionalBatch=document.createElement('details');additionalBatch.className='batch-additional';additionalBatch.innerHTML='<summary>Additional human factors</summary><p class="note">Select explicitly to vary these factors. Perception, attention to warnings, stress tolerance and pressure over the task affect the engine; the rest are recorded only.</p><div class="knowledge-grid"></div>';
for(const node of Array.from($('batch-fields').children))if(node.querySelector('[data-batch-field]')?.dataset.batchField.startsWith('humanFactors.'))additionalBatch.querySelector('.knowledge-grid').append(node);
$('batch-fields').append(additionalBatch);
let batchCards=[],batchSettings=[],batchBundles=[];
$('batch-all').onclick=()=>document.querySelectorAll('[data-batch-field]').forEach(input=>input.checked=true);
$('batch-none').onclick=()=>document.querySelectorAll('[data-batch-field]').forEach(input=>input.checked=false);
$('batch-generate').onclick=async()=>{
  if(!builder || !token){$('batch-status').textContent='Please wait for the local studio to finish loading.';return;}
  const count=Number($('batch-count').value);
  const fields=Array.from(document.querySelectorAll('[data-batch-field]:checked'),input=>input.dataset.batchField);
  if(!Number.isInteger(count)||count<1||count>200||!fields.length){$('batch-status').textContent='Select at least one parameter to vary and choose 1–200 personas.';return;}
  const baseline=PersonaParameters.validate(parameters);
  const role=batchRole();
  const referenceIds=Array.from(document.querySelectorAll('[data-role-reference]:checked'),input=>input.dataset.roleReference);
  const references=role.references.filter(r=>referenceIds.includes(r.id));
  if(!references.length){$('batch-status').textContent='Add and select at least one real participant reference for this role.';return;}
  $('batch-generate').disabled=true;$('batch-save').hidden=true;$('batch-download').hidden=true;
  $('batch-results').textContent='';batchCards=[];batchSettings=[];batchBundles=[];
  $('batch-status').textContent='AI is planning variations, then each card will be checked. This may take a few minutes…';
  try{
    const result=await request('/api/generate-batch',{count:Math.min(200,count*3),requestedCount:count,fields,instructions:$('batch-instructions').value,baseline,role:{title:role.title,background:role.background},references});
    const includeConfiguration=fields.some(f=>f.startsWith('humanFactors.'));
    const signatures=excludedRoleSignatures(role,includeConfiguration);
    const rows=[];
    for(const changes of result.variants){
      const index=rows.length;
      const p=JSON.parse(JSON.stringify(baseline));
      for(const [path,value] of Object.entries(changes)){
        if(!fields.includes(path))throw Error('AI changed an unselected parameter. The result was rejected.');
        if(path.startsWith('humanFactors.'))p.humanFactors[path.split('.')[1]]=value;
        else if(path.startsWith('knowledge.'))PersonaParameters.setGroup(p,path.split('.')[1],value);
        else p[path]=value;
      }
      p.name=baseline.name.slice(0,70)+' · '+String(index+1).padStart(3,'0');
      const built=PersonaParameters.build(PersonaParameters.validate(p),builder,flow);
      const signature=cardSignature(built.card,includeConfiguration);
      if(signatures.has(signature))continue;
      signatures.add(signature);
      rows.push({p,card:built.card,changes,built,signature});
      if(rows.length===count)break;
    }
    if(rows.length<count)throw Error(`Only ${rows.length} new profiles were found in this candidate batch after excluding reference and existing cards. Retry, select more variable parameters, or reduce the count. No partial batch was saved.`);
    role.generated.push(...rows.map(r=>r.signature));persistRoles();
    batchCards=rows.map(r=>r.card);batchSettings=rows.map(r=>r.p);batchBundles=rows.map(r=>r.built);
    $('batch-status').textContent=`Generated ${rows.length} distinct persona cards. ${result.summary} These are synthetic test personas.`;
    $('batch-results').innerHTML=rows.map((r,i)=>`<details><summary>${escapeHTML(r.p.name)}</summary><p class="note">${Object.entries(r.changes).map(([key,value])=>`${escapeHTML(batchFields.find(f=>f[0]===key)?.[1]||key)}: ${escapeHTML(JSON.stringify(value))}`).join(' · ')}</p><button class="button secondary" data-batch-load="${i}">Load in editor</button><button class="button secondary" data-batch-card="${i}">Download engine JSON</button></details>`).join('');
    $('batch-download').hidden=false;$('batch-save').hidden=false;
  }catch(error){$('batch-status').textContent=error.message;}
  finally{$('batch-generate').disabled=false;update();}
};
$('batch-results').onclick=event=>{
  const load=event.target.dataset.batchLoad,card=event.target.dataset.batchCard;
  if(load!==undefined){parameters=PersonaParameters.validate(batchSettings[Number(load)]);controls();update();$('behavior-section').scrollIntoView({behavior:'smooth'});}
  if(card!==undefined)download(`persona-${Number(card)+1}.json`,batchCards[Number(card)]);
};
$('batch-download').onclick=()=>download('persona-batch.json',{format:'sue-persona-batch',version:1,cards:batchCards});
$('batch-save').onclick=async()=>{
  $('batch-save').disabled=true;$('batch-generate').disabled=true;
  let saved=0;
  try{for(let i=0;i<batchCards.length;i++){await request('/api/save',batchBundles[i]);saved++;$('batch-status').textContent=`Saving ${saved}/${batchCards.length}`;}$('batch-status').textContent=`Saved ${saved} individual JSON files to local data/personas, ready for the original engine.`;}
  catch(error){$('batch-status').textContent=`Saved ${saved} files. ${error.message}`;}
  finally{$('batch-save').disabled=false;$('batch-generate').disabled=false;}
};

function batchChoices(path){
  if(path.startsWith('humanFactors.'))return PersonaParameters.HUMAN_FACTORS.find(f=>'humanFactors.'+f.key===path).choices;
  const group=PersonaParameters.GROUPS.find(g=>'knowledge.'+g.key===path);
  if(group)return (group.word?['Unknown','Everyday meaning','Technical understanding']:['Unknown','Vaguely known','Understood']).map((label,value)=>[value,label]);
  if([...FIELDS,...STATE_FIELDS].some(f=>f.key===path))return SCORES.map(v=>[v,String(v)]);
  const options={english:['beginner','intermediate','fluent'],vocabSize:[null,500,2000,5000,10000,20000,30000,40000],urgency:['calm','urgent'],stakes:['low','high'],ifConfirmMissing:['let_go','check','redo'],confirmBy:WAYS.map(w=>[w[0]])};
  return options[path].map(v=>[v,v===null?'Auto':Array.isArray(v)?v.join(', '):String(v)]);
}
function renderBatchBaselines(){
  document.querySelectorAll('[data-batch-base]').forEach(select=>{const path=select.dataset.batchBase,[group,key]=path.split('.'),value=key?parameters[group][key]:parameters[path],choices=batchChoices(path);if(!choices.some(([v])=>JSON.stringify(v)===JSON.stringify(value)))choices.push([value,JSON.stringify(value)]);select.innerHTML=choices.map(([v,label])=>`<option value="${escapeHTML(JSON.stringify(v))}" ${JSON.stringify(v)===JSON.stringify(value)?'selected':''}>${escapeHTML(label)}</option>`).join('');});
}
$('batch-fields').addEventListener('change',event=>{const path=event.target.dataset.batchBase;if(!path)return;const value=JSON.parse(event.target.value);if(path.startsWith('knowledge.'))PersonaParameters.setGroup(parameters,path.split('.')[1],value);else if(path.startsWith('humanFactors.'))parameters.humanFactors[path.split('.')[1]]=value;else parameters[path]=value;controls();update();});
renderBatchBaselines();
