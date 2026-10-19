/* Role library is editor metadata. Engine cards and engine rules stay unchanged. */
'use strict';
const ROLE_STORAGE='sue-role-library-v1';
const initialRoles=[
  {id:'it-project',title:'IT / Technology Project Manager',background:'IT or technology project management experience. Monitors project spend and budgets; understands basic IT/cloud concepts without necessarily being a cloud engineer. Cloud-billing familiarity varies. Goals: control spend and avoid surprises. Exact interface knowledge must be established from participant evidence.'},
  {id:'finops',title:'FinOps / Cloud Cost Administrator',background:'Responsible for cloud cost oversight, budgets and reporting. Establish actual terminology and interface knowledge from individual interviews; do not assume mastery from the role title.'},
  {id:'engineering',title:'Engineer with Budget Responsibilities',background:'Engineering work with responsibility for project spending. Product-specific billing knowledge and financial decision habits require participant evidence.'}
].map(role=>({...role,baseline:PersonaParameters.defaults(),references:[],generated:[]}));
let roleLibrary={version:1,selected:'it-project',roles:initialRoles};
function validateRoleLibrary(data){
  if(data?.version!==1||!Array.isArray(data.roles)||!data.roles.length||data.roles.length>100)throw Error('Invalid role library.');
  const ids=new Set();
  for(const role of data.roles){
    if(typeof role.id!=='string'||ids.has(role.id)||typeof role.title!=='string'||!role.title.trim()||role.title.length>100||typeof role.background!=='string'||role.background.length>4000)throw Error('Invalid role definition.');
    ids.add(role.id);role.baseline=PersonaParameters.validate(role.baseline);
    if(!Array.isArray(role.references)||role.references.length>200||!Array.isArray(role.generated)||role.generated.length>20000||role.generated.some(s=>typeof s!=='string'))throw Error('Invalid role records.');
    const refIds=new Set();for(const r of role.references){if(typeof r.id!=='string'||refIds.has(r.id)||typeof r.name!=='string'||r.name.length>100||typeof r.text!=='string'||r.text.length>30000)throw Error('Invalid participant record.');refIds.add(r.id);if(r.parameters)r.parameters=PersonaParameters.validate(r.parameters);if(r.card&&(!r.card.items||!r.card.tendency||!r.card.persona))throw Error('Invalid reference card.');}
  }
  if(!ids.has(data.selected))throw Error('Select a valid role.');return data;
}
try{const saved=localStorage.getItem(ROLE_STORAGE);if(saved)roleLibrary=validateRoleLibrary(JSON.parse(saved));}catch(error){$('role-status').textContent='Saved role library could not be loaded. Import your backup to restore it.';}
function persistRoles(){try{localStorage.setItem(ROLE_STORAGE,JSON.stringify(roleLibrary));}catch(error){throw Error('Could not store the role library. Export a backup; browser storage may be full.');}}
function activeRole(){return roleLibrary.roles.find(r=>r.id===roleLibrary.selected);}
function batchRole(){return roleLibrary.roles.find(r=>r.id===$('batch-role-select').value)||activeRole();}
function cardSignature(card,includeConfiguration=false){
  // Scores, states and perception all change what the engine does (engine-design.md 4.9).
  const levels=[...FIELDS.map(f=>card.tendency[f.key]?.score ?? card.tendency[f.key]?.level),card.state,card.perception];
  const items=card.items.map(i=>[i.id,i.result]).sort((a,b)=>a[0].localeCompare(b[0]));
  const meanings=(card.screens||[]).flatMap(s=>s.words||[]).map(w=>[w.id,w.level,w.gloss||'']).sort((a,b)=>a[0].localeCompare(b[0]));
  const lang=card.persona.lang||{};
  return JSON.stringify({configuration:includeConfiguration?Object.fromEntries(PersonaParameters.HUMAN_FACTORS.map(f=>[f.key,card.persona.studioFactors?.values?.[f.key]||'unspecified'])):undefined,levels,items,meanings,english:lang.english,vocab:lang.vocabSize??({beginner:500,intermediate:2000,fluent:20000}[lang.english]),completion:[...(card.goal.confirmBy||[])].sort(),missing:card.goal.ifConfirmMissing,situation:card.goal.situation});
}
function referenceCard(r){return r.parameters?PersonaParameters.build(r.parameters,builder,flow).card:r.card;}
function excludedRoleSignatures(role,includeConfiguration=false){const seen=new Set(role.generated);for(const r of role.references){const c=referenceCard(r);if(c)seen.add(cardSignature(c,includeConfiguration));}return seen;}
function renderBatchReferences(){
  const role=batchRole();$('batch-role-description').textContent=role.background;
  $('batch-reference-select').innerHTML=role.references.length?'<p class="note">Choose participant evidence to send to AI. All reference cards are excluded from duplicates, even if unchecked.</p>'+role.references.map(r=>`<label class="check-choice"><input type="checkbox" data-role-reference="${escapeHTML(r.id)}" checked><span>${escapeHTML(r.name)} <small>${r.parameters||r.card?'Profile parameters available':'Interview text only — settings not reviewed'}</small></span></label>`).join(''):'<p class="note">No real participant records yet. Add references above before evidence-based batch generation.</p>';
}
function renderRoles(){
  const options=roleLibrary.roles.map(r=>`<option value="${escapeHTML(r.id)}">${escapeHTML(r.title)}</option>`).join('');
  $('role-select').innerHTML=options;$('role-select').value=roleLibrary.selected;
  $('batch-role-select').innerHTML=options;$('batch-role-select').value=roleLibrary.selected;
  const role=activeRole();$('role-background').textContent=role.background;
  $('role-references').innerHTML=role.references.map(r=>`<details><summary>${escapeHTML(r.name)} · ${r.parameters||r.card?'Profile':'Interview'}</summary><p class="note">${escapeHTML(r.text||'No interview text attached.')}</p>${r.text?`<button class="button secondary" data-ref-text="${escapeHTML(r.id)}">Load interview into editor</button>`:''}${r.parameters?`<button class="button secondary" data-ref-load="${escapeHTML(r.id)}">Load reference settings</button>`:''}<button class="button secondary" data-ref-remove="${escapeHTML(r.id)}">Remove reference</button></details>`).join('');renderBatchReferences();
}
function roleMessage(message){$('role-status').textContent=message;}
$('role-select').onchange=()=>{roleLibrary.selected=$('role-select').value;parameters=PersonaParameters.validate(activeRole().baseline);controls();update();persistRoles();renderRoles();roleMessage('Role baseline loaded. Adjust individual traits below; role labels do not grant knowledge.');};
$('batch-role-select').onchange=renderBatchReferences;
$('role-update-baseline').onclick=()=>{try{activeRole().baseline=PersonaParameters.validate(parameters);persistRoles();roleMessage('Current editor settings saved as this role’s baseline. Participant records are unchanged.');}catch(e){roleMessage(e.message);}};
$('role-create').onclick=()=>{try{const title=$('role-title').value.trim(),background=$('role-description').value.trim();if(!title||!background)throw Error('Enter a title and shared background.');const id=crypto.randomUUID();roleLibrary.roles.push({id,title,background,baseline:PersonaParameters.validate(parameters),references:[],generated:[]});roleLibrary.selected=id;persistRoles();renderRoles();roleMessage('Custom role created using the current editor settings as its baseline.');}catch(e){roleMessage(e.message);}};
$('role-capture').onclick=()=>{try{const name=$('reference-name').value.trim();if(!name)throw Error('Enter a participant ID or pseudonym.');if(!bundle)throw Error('Wait for the card compiler.');const role=activeRole();role.references.push({id:crypto.randomUUID(),name,text:$('profile-text').value,parameters:PersonaParameters.validate(parameters)});persistRoles();renderRoles();roleMessage('Reviewed settings added as a reference. This label records your confirmation; it is not an automatic accuracy certification.');}catch(e){roleMessage(e.message);}};
$('role-references').onclick=event=>{try{const textId=event.target.dataset.refText;if(textId){const r=activeRole().references.find(r=>r.id===textId);$('profile-text').value=r.text;$('reference-name').value=r.name;$('interview-section').scrollIntoView({behavior:'smooth'});profileMessage('Reference interview loaded. Extract and review settings, then add a reviewed profile reference.');}const id=event.target.dataset.refLoad,remove=event.target.dataset.refRemove,role=activeRole();if(id){const r=role.references.find(r=>r.id===id);parameters=PersonaParameters.validate(r.parameters);$('profile-text').value=r.text;controls();update();}if(remove){role.references=role.references.filter(r=>r.id!==remove);persistRoles();renderRoles();}}catch(e){roleMessage(e.message);}};
$('role-import').onclick=()=>$('role-files').click();
$('role-files').onchange=async()=>{try{const role=activeRole(),records=[];for(const file of $('role-files').files){if(file.size>500000)throw Error('Keep each file under 500 KB.');const text=await file.text();const r={id:crypto.randomUUID(),name:file.name.slice(0,100),text:''};if(file.name.toLowerCase().endsWith('.json')){const data=JSON.parse(text);if(data.format==='sue-studio-settings')r.parameters=PersonaParameters.fromJSON(text);else if(data.format==='sue-persona'&&data.version===2){if(!Array.isArray(data.items)||!data.tendency||!data.persona||!data.goal)throw Error('Incomplete persona card.');r.card=data;r.name=(data.persona.name||file.name).slice(0,100);}else if(data.parameters){r.parameters=PersonaParameters.validate(data.parameters);r.text=typeof data.transcript==='string'?data.transcript:'';}else if(typeof(data.transcript??data.text)==='string')r.text=data.transcript??data.text;else throw Error('Import settings, a persona card, or transcript JSON.');}else r.text=text;if(r.text.length>30000)throw Error('Keep interviews under 30,000 characters.');records.push(r);}role.references.push(...records);validateRoleLibrary(roleLibrary);persistRoles();renderRoles();roleMessage(`Imported ${records.length} participant records. Text-only records are evidence, not calibrated parameter profiles.`);}catch(e){roleMessage(e.message);}finally{$('role-files').value='';}};
$('role-export').onclick=()=>download('persona-role-library.json',roleLibrary);
$('role-import-library').onclick=()=>$('role-library-file').click();
$('role-library-file').onchange=async()=>{try{const file=$('role-library-file').files[0];if(!file||file.size>20000000)throw Error('Choose a role library under 20 MB.');const next=validateRoleLibrary(JSON.parse(await file.text()));roleLibrary=next;persistRoles();renderRoles();roleMessage('Role library restored.');}catch(e){roleMessage(e.message);}finally{$('role-library-file').value='';}};
renderRoles();
