'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const token = document.querySelector('meta[name="workflow-token"]').content;
  const labels = ['Source files', 'Output folders', 'Review & browser', 'Run preferences', 'Check setup', 'Run workflow'];
  const descriptions = ['Connect the source documents and case lists for your next review.', 'Keep working files, review results and diagnostics organised.', 'Connect your review instructions and dedicated Copilot browser.', 'Define your review scope and choose how cases are processed.', 'Verify your files, browser and dependencies before starting.', 'Monitor your document review and open the completed results.'];
  let config = {}, defaults = {}, groups = [], models = [], state = {}, step = 0;
  let cursor = 0, activity = [], pollTimer, inFlight = false, dirty = false, master = false, cleanup = false;
  let lastCheckSignature = '', lastStatusSignature = '', lastModelSignature = '';
  function escape(value) { return String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function eventTime(value) { if(!value)return ''; const date=new Date(typeof value==='number'?value*1000:value);return Number.isNaN(date.getTime())?'':date.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
  function modelLabel() { return models.find((m) => m.id === config.default_model)?.label || 'GPT-6 Sol'; }
  function notice(message, error = false) { $('notice').textContent = message; $('notice').hidden = !message; $('notice').classList.toggle('error', error); }
  async function api(path, data) {
    const response = await fetch('/api/' + path, { method: data === undefined ? 'GET' : 'POST', headers: {'X-Workflow-Token': token, ...(data === undefined ? {} : {'Content-Type':'application/json'})}, ...(data === undefined ? {} : {body: JSON.stringify(data)}), cache: 'no-store' });
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.error || result.message || 'The request could not be completed.');
    return result;
  }
  async function action(fn) { try { await fn(); } catch (error) { notice(error.message, true); } }
  function readConfig() {
    document.querySelectorAll('[data-config]').forEach((input) => {
      const key = input.dataset.config;
      config[key] = input.type === 'checkbox' ? input.checked : input.type === 'number' ? Number(input.value) : input.value;
    });
    config.default_model = $('default-model').value || config.default_model;
    return {...config};
  }
  function changed() {
    readConfig(); dirty = true; state.ready = false; $('save-status').textContent = 'Unsaved changes';
    $('notice').hidden = true; updateScope(); updateControls();
    $('model-availability').hidden=true;lastModelSignature='';
    if(step===5)document.querySelector('.metric:last-child strong').textContent=modelLabel();
  }
  function buildNavigation() {
    $('navigation').innerHTML = labels.map((label, i) => `<button class="nav-step" data-step="${i}"><span class="step-number">${String(i+1).padStart(2,'0')}</span>${escape(label)}</button>`).join('');
    $('navigation').addEventListener('click', (event) => { const target = event.target.closest('[data-step]'); if (target && !state.busy) navigate(Number(target.dataset.step)); });
  }
  function field(spec) {
    return `<div class="field ${spec.kind.includes('dir') ? 'wide' : ''}"><label for="field-${escape(spec.key)}">${escape(spec.label)}${spec.key === 'edge_executable' ? ' <span class="mini-caption">OPTIONAL</span>' : ''}</label><div class="input-row"><input id="field-${escape(spec.key)}" data-config="${escape(spec.key)}" value="${escape(config[spec.key])}" aria-describedby="help-${escape(spec.key)}" spellcheck="false" autocomplete="off"><button type="button" class="browse" data-browse="${escape(spec.key)}" aria-label="Browse for ${escape(spec.label)}">Browse</button></div><span id="help-${escape(spec.key)}" class="field-help">${escape(spec.guidance)}</span>${spec.key === 'edge_executable' ? '<button type="button" class="text-button" id="auto-edge">Detect automatically</button>' : ''}</div>`;
  }
  function scope() {
    const specs = [['start_batch','First case ID',1,999999999,100],['batch_count','100-case batches',1,10,1],['cases_to_process','Cases to review',1,1000,1],['browser_tabs','Copilot browser tabs',1,6,1]];
    return `<section class="card"><div class="card-heading"><div><h2>Review scope</h2><p>Choose the cases and browser capacity for this run.</p></div><span class="mini-caption">UP TO 6 TABS</span></div><div class="card-body"><div class="fields">${specs.map(([key,label,min,max,increment]) => `<div class="field"><label for="field-${key}">${label}</label><input id="field-${key}" type="number" data-config="${key}" min="${min}" max="${max}" step="${increment}" value="${escape(config[key])}"></div>`).join('')}<div class="field"><label for="field-processing_flow">Processing flow</label><select id="field-processing_flow" data-config="processing_flow"><option value="1" ${config.processing_flow==='1'?'selected':''}>Prepare and send each tab</option><option value="2" ${config.processing_flow==='2'?'selected':''}>Prepare all tabs, then send (legacy)</option></select></div><div class="field"><label for="field-edge_debug_port">Browser connection port</label><input id="field-edge_debug_port" type="number" min="1024" max="65535" data-config="edge_debug_port" value="${escape(config.edge_debug_port)}"><span class="field-help">Keep the default unless your browser uses a different port.</span></div></div><p class="scope-summary" id="scope-summary"></p></div></section><section class="card"><div class="card-heading"><h2>Run options</h2><button class="text-button" id="restore">Restore defaults</button></div><div class="card-body"><div class="options"><label class="option"><input type="checkbox" id="cleanup" ${cleanup?'checked':''}> Clean temporary files outside this batch</label><label class="option"><input type="checkbox" data-config="diagnostic_mode" ${config.diagnostic_mode?'checked':''}> Detailed activity</label></div><div class="note">Temporary-file cleanup shows a preview and asks for confirmation before removing files.</div></div></section>`;
  }
  function checksPage() {
    return `<section class="card"><div class="card-heading"><div><h2>Workspace readiness</h2><p>Check your files and output access. Review any warnings before you run.</p></div><span class="badge">PREFLIGHT</span></div><div class="card-body"><div id="checks" class="checks"></div><div class="check-actions"><button id="check" class="button primary">Check setup</button><span id="check-status"></span></div></div></section><div class="note">You can return to any setup step to update a location. Changing a setting requires a new setup check.</div>`;
  }
  function runPage() {
    return `<section class="card"><div class="metrics"><div class="metric"><label>Cases to review</label><strong>${escape(config.cases_to_process)}</strong></div><div class="metric"><label>Copilot tabs</label><strong>${escape(config.browser_tabs)}</strong></div><div class="metric"><label>Default model · all cases</label><strong>${escape(modelLabel())}</strong></div></div><div class="run-banner"><span class="dot"></span><div class="run-status"><strong id="run-status">Ready when you are</strong><span id="run-detail">Check setup before starting your review.</span></div><button class="button primary" id="start">${master?'Build master workbooks':'Start document review'}</button><button class="button danger" id="stop" hidden>Stop safely</button></div></section>${master?'<div class="note">Master workbooks are built from complete, readable 100-case batches of completed analyses. Existing master workbooks may be replaced after checking.</div>':'<div class="stage-track" aria-label="Review stages"><span data-stage="prepare">01 · Prepare cases</span><span data-stage="merge">02 · Create PDFs</span><span data-stage="copilot">03 · Copilot review</span></div>'}<section class="card activity-card"><div class="card-heading"><div><h2>Run activity</h2><p>Recent updates from your review workflow.</p></div><div class="result-actions"><button class="button secondary" data-open="analysis_output_dir">Open results ↗</button><button class="button secondary" data-open="diagnostics_dir">Open logs ↗</button></div></div><ol class="activity" id="activity"></ol><div id="activity-empty" class="activity-empty">No activity yet. Updates appear here when a check or run starts.</div></section>`;
  }
  function navigate(index, useMaster = false, collect = true) {
    if(collect)readConfig(); step = index; master = useMaster; lastCheckSignature = ''; lastStatusSignature = '';
    $('page-title').textContent = useMaster ? 'Master workbooks' : labels[index];
    $('page-description').textContent = useMaster ? 'Bring completed analyses together into review workbooks.' : descriptions[index];
    $('step-caption').textContent = useMaster ? 'COMPLETED ANALYSES' : `STEP ${String(index+1).padStart(2,'0')} / 06`;
    $('breadcrumb-current').textContent = useMaster ? 'Master workbooks' : labels[index];
    document.querySelectorAll('[data-step]').forEach((button) => { const active = Number(button.dataset.step) === index && !master; button.classList.toggle('active',active); if(active) button.setAttribute('aria-current','step'); else button.removeAttribute('aria-current'); });
    $('page-content').innerHTML = index < 4 ? `<section class="card"><div class="card-heading"><div><h2>${escape(groups[index]?.title || labels[index])}</h2><p>${escape(groups[index]?.description || '')}</p></div><span class="mini-caption">${index===3?'TRACKING FILES':'WORKSPACE SETTINGS'}</span></div><div class="card-body fields">${(groups[index]?.fields || []).map(field).join('')}</div></section>${index===3?scope():''}` : index === 4 ? checksPage() : runPage();
    $('page-content').classList.remove('content-enter'); void $('page-content').offsetWidth; $('page-content').classList.add('content-enter');
    bindPage(); updateScope(); renderState(); $('page-title').scrollIntoView({block:'nearest'});
  }
  function bindPage() {
    $('page-content').querySelectorAll('[data-config]').forEach((input) => input.addEventListener('input',changed));
    document.querySelectorAll('[data-browse]').forEach((button) => button.addEventListener('click', () => action(async () => { button.disabled = true; try { const result = await api('browse',{key:button.dataset.browse,current:config[button.dataset.browse]}); if(result.path){config[button.dataset.browse]=result.path; $(`field-${button.dataset.browse}`).value=result.path; changed();} } finally {button.disabled=!!state.busy;} })));
    document.querySelectorAll('[data-open]').forEach((button) => button.addEventListener('click', () => action(async () => { await api('open',{key:button.dataset.open,config:readConfig()}); })));
    $('auto-edge')?.addEventListener('click', () => { $('field-edge_executable').value = ''; changed(); });
    $('cleanup')?.addEventListener('change', (event) => {cleanup=event.target.checked;});
    $('restore')?.addEventListener('click', () => action(async () => { if(await confirmDialog('Restore default settings?', 'Your current selections will be replaced with the workspace defaults.', 'Restore defaults')) {config={...defaults}; $('default-model').value=config.default_model; dirty=true; state.ready=false; navigate(3,false,false); $('save-status').textContent='Unsaved changes';} }));
    $('check')?.addEventListener('click', () => action(preflight));
    $('start')?.addEventListener('click', () => action(start));
    $('stop')?.addEventListener('click', () => action(async () => { acceptState(await api('stop',{})); state.stop_requested=true;updateControls(); notice('Stop requested. The workflow will stop at a safe boundary.'); schedulePoll(200); }));
  }
  function updateScope() { if($('scope-summary')){ const start=Number(config.start_batch), end=start+Number(config.batch_count)*100-1; $('scope-summary').textContent=`Case IDs ${start.toLocaleString()}–${end.toLocaleString()} · ${Number(config.cases_to_process).toLocaleString()} cases to review · ${config.browser_tabs} browser tabs`; } }
  async function save() { const result=await api('config',{config:readConfig()}); if(result.config) config=result.config; dirty=false; acceptState(result); $('save-status').textContent='Settings saved'; notice('Your settings have been saved.'); }
  async function preflight() { readConfig(); navigate(4); notice('');const result=await api('preflight',{config:readConfig()});dirty=false; acceptState(result); $('save-status').textContent='Settings saved'; schedulePoll(150); }
  function confirmDialog(title, text, label, paths, requireText) {
    return new Promise((resolve) => {
      $('modal-title').textContent=title; $('modal-body').innerHTML=`<p>${escape(text)}</p>${paths?`<pre class="modal-paths">${escape(paths)}</pre>`:''}${requireText?'<label for="confirm-text">Type DELETE to allow cleanup</label><input class="confirm-input" id="confirm-text" autocomplete="off" spellcheck="false">':''}`;
      $('modal-confirm').textContent=label; $('modal-confirm').disabled=!!requireText; $('modal-confirm').hidden=false;
      $('confirm-text')?.addEventListener('input',(event)=>{$('modal-confirm').disabled=event.target.value!=='DELETE';});
      $('modal').returnValue='cancel';
      const guard=(event)=>{if(requireText&&event.submitter?.value==='confirm'&&$('confirm-text')?.value!=='DELETE')event.preventDefault();};
      $('modal').querySelector('form').addEventListener('submit',guard);
      $('modal').addEventListener('close',()=>{$('modal').querySelector('form').removeEventListener('submit',guard);resolve($('modal').returnValue==='confirm'&&(!requireText||$('confirm-text')?.value==='DELETE'));},{once:true}); $('modal').showModal();
    });
  }
  async function start() {
    readConfig();
    if(!master&&(!state.ready||dirty)){navigate(4);notice('Run a successful setup check before starting.',true);return;}
    const data={config:readConfig(),mode:master?'master':'primary',cleanup:false};
    if(master){if(!await confirmDialog('Build master workbooks?', 'Only complete, readable 100-case batches are built. Missing files are listed. Existing master workbooks may be replaced.', 'Build workbooks')) return;data.master_confirmed=true;}
    else {
      if(!await confirmDialog('Save your Office work', 'Conversion may open Office apps. Save your work and avoid editing source documents during the run.', 'Start review'))return;
      data.office_acknowledged=true;
      if(cleanup){const preview=await api('cleanup-preview',{config:readConfig()});const paths=(preview.targets||[]).map((item)=>typeof item==='string'?item:JSON.stringify(item)).join('\n')||'No recognised out-of-range targets currently found.';if(!await confirmDialog('Confirm temporary-file cleanup', `${preview.count} recognised temporary items outside your batch will be removed. Review these locations before continuing.`, 'Allow cleanup',paths,true))return;data.cleanup=true;data.cleanup_confirmation='DELETE';}
    }
    notice('');state.stop_requested=false; acceptState(await api('start',data)); schedulePoll(150);
  }
  function acceptState(result) { const next=result.state || (result.status!==undefined?result:null); if(next){state={...state,...next}; if(dirty)state.ready=false; if(next.events){for(const event of next.events){if(event.id>cursor){activity.push(event);cursor=Math.max(cursor,event.id);}}activity=activity.slice(-500);} if(next.cursor)cursor=Math.max(cursor,next.cursor); renderState();} }
  function renderState() {
    updateControls();
    const report=dirty?null:state.model_checks;
    if(report&&!state.busy&&$('notice').textContent.startsWith('Checking models')){const available=(report.models||[]).filter((model)=>model.selected).length;notice(report.error||`Model check complete: ${available} of ${(report.models||[]).length} models could be selected in this Copilot session.`,!!report.error);}
    const modelSignature=JSON.stringify(report);
    if(modelSignature!==lastModelSignature){lastModelSignature=modelSignature;
      $('model-availability').hidden=!report;
      if(report){const pending=report.status==='checking'||report.status==='running';$('model-availability').innerHTML=`<div class="card-heading"><div><h2>Live model availability</h2><p>${pending?'Checking each model in your dedicated Copilot browser…':'Availability from your current Copilot session. Recheck after changing your account or browser profile.'}</p>${report.account_context||report.copilot_plan?`<p><strong>Signed-in session:</strong> ${escape(report.account_context||'Account not identified')}${report.copilot_plan?` · ${escape(report.copilot_plan)}`:''}</p>`:''}</div></div><div class="card-body">${report.error?`<div class="notice error">${escape(report.error)}<br>Sign in to Copilot in your dedicated Edge session, then check again.</div>`:''}<div class="model-check-grid">${(report.models||[]).map((model)=>`<div class="model-check-row"><strong>${escape(model.label)}</strong><span class="${model.selected?'ok':'warning'}">${model.selected?'Available':'Not verified'}</span><span class="mini-caption">${model.selection_ms!=null?`${escape(model.selection_ms)} ms`:''}</span>${model.error?`<p class="field-help">${escape(model.error)}</p>`:''}</div>`).join('')}</div>${pending?'<p class="field-help">The check opens the model picker and restores your chosen default. Keep the Copilot session open.</p>':''}</div>`;}
    }
    if($('checks')){
      const signature=JSON.stringify([state.checks,state.checking,state.ready,dirty]);
      if(signature!==lastCheckSignature){lastCheckSignature=signature;const checks=dirty?[]:(state.checks||[]);$('checks').innerHTML=checks.length?checks.map((check)=>`<details class="check"><summary><span class="${escape(check.level)}">${check.level==='ok'?'✓':check.level==='error'?'!':'△'}</span><strong>${escape(check.name)}</strong><span class="check-status ${escape(check.level)}">${check.level==='ok'?'Ready':check.level==='warning'?'Review':'Needs attention'}</span></summary><p>${escape(check.detail)}</p></details>`).join(''):'<div class="note">Check your source files, output locations, review instructions and required dependencies.</div>';$('check-status').textContent=state.checking?'Checking your workspace…':state.ready?'Your workspace is ready.':checks.some((c)=>c.level==='error')?'Resolve the requirements above and check again.':'Not checked';}
    }
    if($('run-status')){
      const signature=JSON.stringify([state.status,state.busy,state.ready,activity.length,cursor]);
      if(signature!==lastStatusSignature){lastStatusSignature=signature;$('run-status').textContent=state.status||'Ready when you are';$('run-detail').textContent=state.running?'Review in progress. Keep the dedicated Copilot session open.':state.ready?'Workspace checked. Ready to start.':'Check setup before starting your review.';
        const visible=activity.filter((event)=>event.kind!=='log'||config.diagnostic_mode);$('activity').innerHTML=visible.map((event)=>`<li><time>${escape(eventTime(event.time))}</time><span class="activity-message ${['error','warning'].includes(event.kind)?escape(event.kind):''}">${escape(event.message)}</span></li>`).join('');$('activity-empty').hidden=visible.length>0;
        const stage=state.stage||[...activity].reverse().find((event)=>event.kind==='stage')?.message;document.querySelectorAll('[data-stage]').forEach((item)=>item.classList.toggle('current',state.running&&item.dataset.stage===stage));
      }
    }
  }
  function updateControls() {
    const busy=!!(state.busy||state.running||state.checking);
    document.querySelectorAll('[data-config],[data-browse],#default-model,#check-models,#save,#restore,#cleanup,#auto-edge,#master-nav,#shutdown').forEach((input)=>{input.disabled=busy;});
    $('back').disabled=busy||step===0; $('next').disabled=busy||(step===4&&(!state.ready||dirty)); $('next').textContent=step<4?'Continue →':step===4?'Go to run →':'Check setup';
    document.querySelectorAll('[data-step]').forEach((button)=>{button.disabled=busy&&Number(button.dataset.step)!==5;});
    if($('check')){$('check').disabled=busy;$('check').textContent=state.checking?'Checking…':'Check setup';}
    if($('start')){$('start').disabled=busy||(!master&&(!state.ready||dirty));$('start').hidden=!!state.running;$('stop').hidden=!state.running;$('stop').disabled=state.mode==='master'||state.stop_requested;}
  }
  function schedulePoll(delay) {clearTimeout(pollTimer);pollTimer=setTimeout(poll,delay??(document.hidden?15000:state.busy||state.running||state.checking?1500:15000));}
  async function poll() {
    if(inFlight){schedulePoll();return;}inFlight=true;
    try{acceptState(await api(`state?after=${cursor}`));$('connection-label').textContent='Workspace connected';$('connection-dot').classList.remove('disconnected');}
    catch(error){$('connection-label').textContent='Connection interrupted';$('connection-dot').classList.add('disconnected');notice('The workspace connection was interrupted. Keep this tab open while it reconnects. '+error.message,true);}
    finally{inFlight=false;schedulePoll();}
  }
  $('default-model').addEventListener('change',changed);
  $('check-models').addEventListener('click',()=>action(async()=>{const result=await api('check-models',{config:readConfig()});if(result.config)config=result.config;dirty=false;acceptState(result);$('save-status').textContent='Settings saved';notice('Checking models in your signed-in Copilot browser. Keep the dedicated session open.');schedulePoll(150);}));
  $('save').addEventListener('click',()=>action(save));
  $('back').addEventListener('click',()=>navigate(Math.max(0,step-1)));
  $('next').addEventListener('click',()=>action(async()=>{if(step<4){readConfig();if(!$('page-content').querySelector('input:invalid')){await save();navigate(step+1);}else{$('page-content').querySelector('input:invalid').reportValidity();}}else if(step===4&&state.ready)navigate(5);else await preflight();}));
  $('master-nav').addEventListener('click',()=>{if(!state.busy)navigate(5,true);});
  $('shutdown').addEventListener('click',()=>action(async()=>{if(await confirmDialog('Close Document Review?',dirty?'Your unsaved settings will be discarded. Close the local workspace application?':'Close the local workspace application?','Close application')){await api('shutdown',{});clearTimeout(pollTimer);$('connection-label').textContent='Application closed';$('page-content').innerHTML='<section class="card"><div class="card-body"><h2>Workspace closed</h2><p>You can close this tab. Use Start Workflow to open the application again.</p></div></section>';document.querySelectorAll('button,select').forEach((control)=>{control.disabled=true;});dirty=false;}}));
  $('support').addEventListener('click',()=>{ $('modal-title').textContent='Help & support';$('modal-body').innerHTML='<div class="support-list"><p><strong>Before a review</strong><br>Choose your source files and output locations, select a model, then run Check setup.</p><p><strong>Copilot sign-in</strong><br>Use the dedicated Edge session for your organisation’s Copilot login. The model picker must offer your selected model.</p><p><strong>If a run needs attention</strong><br>Open diagnostic logs from Run workflow and share the relevant log with your support team. Stop safely before changing your settings.</p><p><strong>While a review runs</strong><br>Keep the dedicated browser session open and avoid editing the source files. This workspace slows its update checks when the tab is in the background.</p></div>';$('modal-confirm').hidden=true;$('modal').querySelector('.modal-actions .secondary').textContent='Close';$('modal').showModal(); });
  $('modal').addEventListener('close',()=>{$('modal').querySelector('.modal-actions .secondary').textContent='Cancel';});
  document.addEventListener('visibilitychange',()=>schedulePoll(document.hidden?15000:100));
  window.addEventListener('beforeunload',(event)=>{if(dirty){event.preventDefault();event.returnValue='';}});
  action(async()=>{const result=await api('bootstrap');config=result.config;defaults=result.defaults;groups=result.groups;models=result.models||[];$('default-model').innerHTML=['GPT','Claude'].map((provider)=>`<optgroup label="${provider}">${models.filter((m)=>String(m.provider).toLowerCase().includes(provider.toLowerCase())).map((m)=>`<option value="${escape(m.id)}">${escape(m.label)}</option>`).join('')}</optgroup>`).join(''); if(!$('default-model').options.length) $('default-model').innerHTML=models.map((m)=>`<option value="${escape(m.id)}">${escape(m.label)}</option>`).join('');$('default-model').value=config.default_model;buildNavigation();acceptState(result);$('demo-badge').hidden=!result.demo;$('version').textContent=result.version?`· ${result.version}`:'';$('connection-label').textContent='Workspace connected';navigate(0);if(result.warning)notice(result.warning,true);schedulePoll();});
})();
