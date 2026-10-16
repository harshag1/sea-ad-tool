(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = location.pathname.replace(/\/?$/, '/');
  const fmt = value => Number(value).toLocaleString('en-US');
  const controls = Object.fromEntries(['subclass','supertype','donor','exclude-reference','extra-filters','genes','layer','limit','engine','donor-split'].map(id => [id,$(id)]));
  const narrow = matchMedia('(max-width:690px)');
  $('parameter-details').open = !narrow.matches;
  narrow.addEventListener('change', event => { $('parameter-details').open = !event.matches; });
  let config;
  let previewController;
  let sampleController;
  let jobsTimer;
  let healthTimer;
  let refreshSequence = 0;
  let jobsActive = false;
  const dropdowns = new Map();
  let opened;
  function message(id, text, error = false) {
    const node = $(id);
    node.textContent = text;
    node.className = `state${error ? ' error' : ''}`;
    node.hidden = !text;
  }
  async function request(path, data, signal) {
    if (typeof path !== 'string' || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(path)) throw new Error('Invalid app resource.');
    const deadline = AbortSignal.timeout(path === 'api/sample' ? 30000 : 12000);
    let response;
    try {
      response = await fetch(new URL(path.replace(/^\/+/, ''), location.origin + base), {method:data === undefined ? 'GET' : 'POST',headers:{Accept:'application/json',...(data === undefined ? {} : {'Content-Type':'application/json'})},body:data === undefined ? undefined : JSON.stringify(data),signal:signal ? AbortSignal.any([signal,deadline]) : deadline});
    } catch(error) {
      if(deadline.aborted) throw new Error('The request took too long. Try a smaller selection or retry.');
      throw error;
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.message || `Request failed (${response.status}).`);
    return result;
  }
  function closeDropdown(focus = false) {
    if (!opened) return;
    const current = opened;
    opened = undefined;
    current.list.hidden = true;
    current.button.setAttribute('aria-expanded','false');
    current.button.removeAttribute('aria-activedescendant');
    if (focus) current.button.focus();
  }
  function syncDropdown(select) {
    const item = dropdowns.get(select);
    item.button.disabled = select.disabled;
    item.button.querySelector('.select-value').textContent = select.selectedOptions[0]?.textContent || 'Select';
    item.list.replaceChildren();
    [...select.options].forEach((option,index) => {
      const node = document.createElement('div');
      node.id = `${select.id}-option-${index}`;
      node.setAttribute('role','option');
      node.setAttribute('aria-selected',String(index === select.selectedIndex));
      node.className = 'select-option';
      node.textContent = option.textContent;
      node.addEventListener('pointerdown', event => event.preventDefault());
      node.addEventListener('click', () => chooseOption(item,index));
      item.list.append(node);
    });
  }
  function highlight(item) {
    [...item.list.children].forEach((node,index) => node.classList.toggle('active',index === item.active));
    const active = item.list.children[item.active];
    if (active) {
      item.button.setAttribute('aria-activedescendant',active.id);
      active.scrollIntoView({block:'nearest'});
    }
  }
  function chooseOption(item,index) {
    const changed = item.select.selectedIndex !== index;
    item.select.selectedIndex = index;
    syncDropdown(item.select);
    closeDropdown(true);
    if (changed) item.select.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function showDropdown(item) {
    if (item.button.disabled) return;
    closeDropdown();
    hideTip();
    opened = item;
    item.active = Math.max(0,item.select.selectedIndex);
    item.button.setAttribute('aria-expanded','true');
    const rect = item.button.getBoundingClientRect();
    const below = innerHeight - rect.bottom - 12;
    const above = rect.top - 12;
    const upward = below < 180 && above > below;
    const height = Math.max(70,Math.min(280,upward ? above : below));
    item.list.style.width = `${Math.min(rect.width,innerWidth-24)}px`;
    item.list.style.left = `${Math.max(12,Math.min(rect.left,innerWidth-rect.width-12))}px`;
    item.list.style.maxHeight = `${height}px`;
    item.list.style.top = upward ? 'auto' : `${rect.bottom + 5}px`;
    item.list.style.bottom = upward ? `${innerHeight-rect.top+5}px` : 'auto';
    item.list.hidden = false;
    highlight(item);
  }
  for (const select of document.querySelectorAll('select')) {
    const wrapper = document.createElement('div');
    wrapper.className = 'select-wrapper';
    select.before(wrapper);
    wrapper.append(select);
    select.classList.add('native-select');
    select.setAttribute('aria-hidden','true');
    select.tabIndex = -1;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'select-button';
    button.id = `${select.id}-button`;
    button.setAttribute('role','combobox');
    button.setAttribute('aria-haspopup','listbox');
    button.setAttribute('aria-expanded','false');
    const label = document.querySelector(`label[for="${select.id}"]`);
    label.id = `${select.id}-label`;
    label.htmlFor = button.id;
    button.setAttribute('aria-labelledby',label.id);
    const value = document.createElement('span');
    value.className = 'select-value';
    const chevron = document.createElement('span');
    chevron.className = 'select-chevron';
    chevron.setAttribute('aria-hidden','true');
    button.append(value,chevron);
    const list = document.createElement('div');
    list.className = 'select-list';
    list.id = `${select.id}-list`;
    list.setAttribute('role','listbox');
    list.setAttribute('aria-labelledby',label.id);
    list.hidden = true;
    button.setAttribute('aria-controls',list.id);
    wrapper.append(button);
    document.body.append(list);
    const item = {select,button,list,active:0,typed:'',timer:undefined};
    dropdowns.set(select,item);
    button.addEventListener('click', () => opened === item ? closeDropdown() : showDropdown(item));
    button.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); closeDropdown(true); return; }
      if (event.key === 'Tab') { closeDropdown(); return; }
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if(opened === item) chooseOption(item,item.active); else showDropdown(item); return; }
      if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
        event.preventDefault();
        const wasOpen = opened === item;
        if (!wasOpen) showDropdown(item);
        if (event.key === 'Home') item.active = 0;
        else if (event.key === 'End') item.active = select.options.length-1;
        else if (wasOpen) item.active = Math.max(0,Math.min(select.options.length-1,item.active+(event.key === 'ArrowDown'?1:-1)));
        highlight(item);
        return;
      }
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        if (opened !== item) showDropdown(item);
        item.typed += event.key.toLowerCase();
        clearTimeout(item.timer);
        item.timer = setTimeout(() => { item.typed = ''; },650);
        const index = [...select.options].findIndex(option => option.textContent.toLowerCase().startsWith(item.typed));
        if (index >= 0) { item.active = index; highlight(item); }
      }
    });
    select.addEventListener('change', () => syncDropdown(select));
    syncDropdown(select);
  }
  document.addEventListener('pointerdown', event => { if(opened && !opened.button.contains(event.target) && !opened.list.contains(event.target)) closeDropdown(); });
  addEventListener('resize', () => closeDropdown());
  addEventListener('scroll', event => { if(opened && !opened.list.contains(event.target)) closeDropdown(); },true);
  const tooltip = $('tooltip');
  let tipTarget;
  function hideTip() { tooltip.hidden = true; if(tipTarget) tipTarget.removeAttribute('aria-describedby'); tipTarget = undefined; }
  function showTip(target) {
    hideTip();
    tipTarget = target;
    tooltip.textContent = target.dataset.tip;
    tooltip.hidden = false;
    target.setAttribute('aria-describedby','tooltip');
    const rect = target.getBoundingClientRect();
    const size = tooltip.getBoundingClientRect();
    tooltip.style.left = `${Math.max(12,Math.min(innerWidth-size.width-12,rect.left+rect.width/2-size.width/2))}px`;
    tooltip.style.top = `${rect.bottom+size.height+12<innerHeight ? rect.bottom+7 : Math.max(12,rect.top-size.height-7)}px`;
  }
  for(const target of document.querySelectorAll('[data-tip]')) {
    target.addEventListener('pointerenter',() => showTip(target));
    target.addEventListener('pointerleave',hideTip);
    target.addEventListener('focus',() => showTip(target));
    target.addEventListener('blur',hideTip);
    target.addEventListener('click',() => showTip(target));
  }
  document.addEventListener('keydown', event => { if(event.key === 'Escape') hideTip(); });
  document.addEventListener('pointerdown', event => { if(tipTarget && !tipTarget.contains(event.target)) hideTip(); });
  $('info-button').addEventListener('click', () => { const open = $('data-notes').hidden; $('data-notes').hidden = !open; $('info-button').setAttribute('aria-expanded',String(open)); });
  const tabs = [...document.querySelectorAll('[role=tab]')];
  function activate(tab,focus = false) {
    closeDropdown(); hideTip();
    for(const item of tabs) {
      const active = item === tab;
      item.setAttribute('aria-selected',String(active));
      item.tabIndex = active ? 0 : -1;
      $(item.getAttribute('aria-controls')).hidden = !active;
    }
    const expression = tab.id !== 'tab-cohort';
    $('expression-controls').hidden = !expression;
    $('preview-button').hidden = expression;
    $('sample-button').hidden = tab.id !== 'tab-expression';
    $('parameter-details').querySelector('summary').textContent = expression ? 'Filters and genes' : 'Filters';
    if(focus) tab.focus();
  }
  tabs.forEach((tab,index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', event => {
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
      activate(tabs[target],true);
    });
  });
  function option(select,value,text) { const node=document.createElement('option'); node.value=String(value); node.textContent=text; select.append(node); }
  function selectedFilters() {
    const filters = {};
    for(const [id,key] of [['subclass','Subclass'],['supertype','Supertype'],['donor','Donor ID']]) if(controls[id].value) filters[key]=controls[id].value;
    if(controls['exclude-reference'].checked) filters['Neurotypical reference']=false;
    if(controls['extra-filters'].value.trim()) {
      let extra;
      try { extra=JSON.parse(controls['extra-filters'].value); } catch { throw new Error('Custom filter must be valid JSON.'); }
      if(!extra || typeof extra!=='object' || Array.isArray(extra)) throw new Error('Custom filter must be a JSON object.');
      if(Object.values(extra).some(value=>value!==null && !['string','number','boolean'].includes(typeof value))) throw new Error('Filter values must be scalar values or null.');
      Object.assign(filters,extra);
    }
    return filters;
  }
  function expressionRequest() {
    const genes = controls.genes.value.trim().split(/[\s,]+/).filter(Boolean);
    if(!genes.length || genes.length > 32) throw new Error('Enter between 1 and 32 gene symbols.');
    return {filters:selectedFilters(),genes,layer:controls.layer.value};
  }
  function invalidateSample() { sampleController?.abort(); $('sample-content').hidden=true; message('sample-state','Read to update expression.'); }
  function invalidatePreview() { previewController?.abort(); $('preview-content').hidden=true; message('preview-state','Apply to update counts.'); invalidateSample(); }
  function cell(row,text,cls) { const node=document.createElement('td'); node.textContent=text; if(cls) node.className=cls; row.append(node); return node; }
  async function preview() {
    let filters;
    try { filters=selectedFilters(); } catch(error) { message('preview-state',error.message,true); return; }
    previewController?.abort();
    const controller=new AbortController(); previewController=controller;
    $('preview-button').disabled=true;
    $('preview-content').hidden=true;
    message('preview-state','');
    $('preview-button').setAttribute('aria-busy','true');
    try {
      const data=await request('api/preview',{filters},controller.signal);
      if(controller.signal.aborted) return;
      $('cell-count').textContent=fmt(data.cells);
      $('donor-count').textContent=fmt(data.groups.length);
      const body=$('donor-rows'); body.replaceChildren();
      const maximum=Math.max(1,...data.groups.map(group=>group.cells));
      for(const group of data.groups) {
        const row=document.createElement('tr');
        cell(row,group.value);
        const plot=cell(row,'');
        const track=document.createElement('div'); track.className='bar-track'; track.setAttribute('role','img'); track.setAttribute('aria-label',`${fmt(group.cells)} cells`);
        const bar=document.createElement('span'); bar.className='bar-fill'; bar.style.width=`${group.cells/maximum*100}%`; track.append(bar); plot.append(track);
        cell(row,fmt(group.cells),'numeric'); body.append(row);
      }
      $('preview-content').hidden=!data.cells;
      message('preview-state',data.cells?'':'No matching cells. Adjust the filters.');
    } catch(error) { if(error.name!=='AbortError') message('preview-state',error.message,true); }
    finally { if(previewController===controller) { $('preview-button').disabled=false; $('preview-button').removeAttribute('aria-busy'); } }
  }
  async function sample() {
    let selection;
    try { selection=expressionRequest(); } catch(error) { message('sample-state',error.message,true); return; }
    sampleController?.abort(); const controller=new AbortController(); sampleController=controller;
    $('sample-button').disabled=true; $('sample-button').setAttribute('aria-busy','true');
    $('sample-content').hidden=true; message('sample-state','Reading…');
    try {
      const data=await request('api/sample',selection,controller.signal);
      if(controller.signal.aborted) return;
      const head=$('sample-head'); const body=$('sample-rows'); head.replaceChildren(); body.replaceChildren();
      const header=document.createElement('tr');
      for(const name of ['Cell','Donor','Subclass',...data.genes]) { const node=document.createElement('th'); node.textContent=name; if(data.genes.includes(name)) node.className='numeric'; header.append(node); }
      head.append(header);
      const maximum=Math.max(1,...data.rows.flatMap(row=>row.values));
      for(const record of data.rows) {
        const row=document.createElement('tr');
        const identifier=document.createElement('span'); identifier.className='cell-id'; identifier.textContent=record.cell_id;
        cell(row,'').append(identifier); cell(row,record.donor); cell(row,record.subclass);
        for(const value of record.values) {
          const node=document.createElement('span'); node.className='expression-value'; node.style.setProperty('--strength',`${Math.sqrt(value/maximum)*24}%`); node.textContent=Number(value).toLocaleString('en-US',{maximumFractionDigits:4});
          cell(row,'','numeric').append(node);
        }
        body.append(row);
      }
      $('sample-note').textContent=`${fmt(data.cells)} cells · ${data.genes.length} genes · ${data.layer === 'UMIs' ? 'UMIs' : 'Normalized'}`;
      message('sample-state',data.cells?'':'No matching cells.'); $('sample-content').hidden=!data.cells;
    } catch(error) { if(error.name!=='AbortError') message('sample-state',error.message,true); }
    finally { if(sampleController===controller) { $('sample-button').disabled=false; $('sample-button').removeAttribute('aria-busy'); } }
  }
  function safeLink(container,path,text) {
    if(typeof path!=='string' || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(path)) return;
    const anchor=document.createElement('a'); anchor.href=new URL(path.replace(/^\/+/,''),location.origin+base); anchor.textContent=text; container.append(anchor);
  }
  function renderJobs(jobs) {
    const list=$('jobs-list'); list.replaceChildren();
    for(const job of jobs) {
      const item=document.createElement('article'); item.className='job'; item.dataset.jobId=job.id;
      const name=document.createElement('div'); name.className='job-title'; name.textContent=job.result ? `${fmt(job.result.n_obs)} cells × ${fmt(job.result.n_vars)} genes` : `${fmt(job.request?.limit || 0)} cells`;
      const status=document.createElement('span'); status.className=`job-status${['error','failed'].includes(job.status)?' error':''}`; status.textContent=job.status;
      item.append(name,status);
      if(job.error) { const error=document.createElement('p'); error.className='job-detail'; error.textContent=job.error; item.append(error); }
      const links=document.createElement('div'); links.className='job-links';
      safeLink(links,job.download_url,'AnnData ↓'); safeLink(links,job.recipe_url,'Recipe ↓'); item.append(links);
      const details=document.createElement('details'); const summary=document.createElement('summary'); summary.textContent='Details'; details.append(summary);
      const detail=document.createElement('p'); detail.className='job-detail'; detail.textContent=[job.id,job.created_at,job.result?.output_bytes ? `${fmt(job.result.output_bytes)} bytes` : null,job.result?.elapsed_seconds ? `${Number(job.result.elapsed_seconds).toFixed(2)} s` : null].filter(Boolean).join(' · '); details.append(detail); item.append(details); list.append(item);
    }
    message('jobs-state',jobs.length?'':'No exports.');
  }
  async function refreshJobs() {
    clearTimeout(jobsTimer);
    const sequence=++refreshSequence;
    try {
      const data=await request('api/exports');
      if(sequence!==refreshSequence) return;
      renderJobs(data.jobs);
      jobsActive=data.jobs.some(job=>['queued','running'].includes(job.status));
      if(jobsActive) jobsTimer=setTimeout(refreshJobs,2500);
    } catch(error) { if(sequence===refreshSequence) { message('jobs-state',error.message,true); if(jobsActive) jobsTimer=setTimeout(refreshJobs,4000); } }
  }
  async function exportSlice(event) {
    event.preventDefault();
    let selection;
    try {
      selection=expressionRequest();
      const limit=Number(controls.limit.value);
      if(!Number.isInteger(limit)||limit<1||limit>10000) throw new Error('Cell limit must be between 1 and 10,000.');
      Object.assign(selection,{limit,engine:controls.engine.value,split_seed:controls['donor-split'].checked?42:null});
    } catch(error) { message('jobs-state',error.message,true); return; }
    $('export-button').disabled=true;
    try { await request('api/exports',selection); await refreshJobs(); }
    catch(error) { message('jobs-state',error.message,true); }
    finally { $('export-button').disabled=false; }
  }
  function populate(data) {
    config=data;
    for(const [id,key] of [['subclass','Subclass'],['supertype','Supertype'],['donor','Donor ID']]) {
      const select=controls[id]; select.replaceChildren();
      if(id!=='subclass') option(select,'',`Any ${id==='donor'?'donor':'supertype'}`);
      for(const entry of data.fields.find(field=>field.name===key)?.values || []) if(entry.value!=null) option(select,entry.value,String(entry.value));
      if(data.defaults.filters[key]!==undefined) select.value=String(data.defaults.filters[key]);
      select.disabled=false; syncDropdown(select);
    }
    controls['exclude-reference'].checked=data.defaults.filters['Neurotypical reference']===false;
    controls.genes.value=data.defaults.genes.join(', ');
    controls.layer.replaceChildren();
    for(const entry of data.source.layers) option(controls.layer,entry.value,entry.value==='UMIs'?'Raw counts':'Normalized');
    controls.layer.value=data.defaults.layer; controls.layer.disabled=false; syncDropdown(controls.layer);
    controls.limit.value=data.defaults.limit;
    $('source-counts').textContent=`${data.source.release} · ${fmt(data.source.n_obs)} cells · ${fmt(data.source.n_vars)} genes`;
    const files=$('files-list'); files.replaceChildren();
    for(const file of data.files || []) { const row=document.createElement('div'); row.className='file'; const name=document.createElement('strong'); name.textContent=file.name; row.append(name); safeLink(row,file.url,'Download ↓'); files.append(row); }
    for(const id of ['preview-button','sample-button','export-button']) $(id).disabled=false;
    $('app-loading').hidden=true;
    $('app-shell').inert=false;
  }
  async function initialize() {
    clearTimeout(healthTimer);
    try {
      const health=await request('health');
      if(health.status==='error') throw new Error(health.message || 'Source unavailable.');
      if(health.status!=='ready') { healthTimer=setTimeout(initialize,2000); return; }
      const data=await request('api/config');
      if(data.status!=='ready') { healthTimer=setTimeout(initialize,2000); return; }
      populate(data); preview(); refreshJobs();
    } catch(error) {
      $('app-loading').hidden=true; $('app-shell').inert=false;
      message('preview-state',error.message || 'Could not connect. Try again.',true);
      const retry=document.createElement('button'); retry.type='button'; retry.className='button'; retry.textContent='Retry'; retry.addEventListener('click',()=>{ $('app-loading').hidden=false; $('app-shell').inert=true; initialize(); }); $('preview-state').append(retry);
    }
  }
  $('cohort-form').addEventListener('submit',event=>{event.preventDefault();preview();});
  $('sample-button').addEventListener('click',sample);
  $('export-form').addEventListener('submit',exportSlice);
  $('refresh-jobs').addEventListener('click',refreshJobs);
  for(const id of ['subclass','supertype','donor','exclude-reference','extra-filters']) controls[id].addEventListener(id==='extra-filters'?'input':'change',invalidatePreview);
  controls.genes.addEventListener('input',invalidateSample);
  controls.layer.addEventListener('change',invalidateSample);
  initialize();
})();
