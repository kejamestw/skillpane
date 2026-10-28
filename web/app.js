const paths = {
  grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  star:'m12 3 2.8 5.7 6.3.9-4.6 4.4 1.1 6.3-5.6-3-5.6 3 1.1-6.3L3 9.6l6.2-.9Z',
  inbox:'M4 4h16l2 11v5H2v-5L4 4Z M2 15h6l2 3h4l2-3h6',
  layers:'m12 3 10 5-10 5L2 8l10-5Z M2 12l10 5 10-5 M2 16l10 5 10-5',
  intersect:'M15 7a6 6 0 1 1-6 10 M9 17a6 6 0 1 1 6-10',
  shield:'m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z m-4 9 3 3 5-6',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3Z',
  sun:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z M12 2v2 m0 16v2 M2 12h2 m16 0h2 M5 5l1.5 1.5 m11 11L19 19 M5 19l1.5-1.5 m11-11L19 5',
  moon:'M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z',
  refresh:'M20 8a8 8 0 0 0-14-3L3 8 M3 3v5h5 M4 16a8 8 0 0 0 14 3l3-3 m0 5v-5h-5',
  search:'M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15Z M16 16l5 5',
  sort:'M4 6h16 M4 12h11 M4 18h6',
  arrow:'M5 12h14 m-6-6 6 6-6 6',
  code:'m8 6-6 6 6 6 m8-12 6 6-6 6 m-3-15-2 18',
  spark:'m12 2 2.8 7.2L22 12l-7.2 2.8L12 22l-2.8-7.2L2 12l7.2-2.8Z',
  file:'M14 2H5v20h14V7l-5-5Z M14 2v5h5 M8 12h8 M8 16h6',
  database:'M21 6c0 2-4 4-9 4S3 8 3 6s4-4 9-4 9 2 9 4Z M3 6v6c0 2 4 4 9 4s9-2 9-4V6 M3 12v6c0 2 4 4 9 4s9-2 9-4v-6',
  copy:'M9 9h12v12H9z M15 5V3H3v12h2',
  check:'m5 12 4 4L19 6',
  close:'m6 6 12 12 M18 6 6 18',
  lock:'M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4 M12 15v2',
  info:'M12 8v.01 M12 11v6 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.grid}"/></svg>`;
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $ = selector => document.querySelector(selector);
const statusLabels = {keep:'保留使用', review:'待檢查', merge:'考慮合併', archive:'考慮封存'};
const views = {
  personal:['我的技能','整理你的工作方式，找到剛好需要的技能。'],
  favorites:['收藏','把常用的工作方式，放在伸手就能找到的地方。'],
  review:['待整理','慢慢釐清用途與分工，每次整理一點。'],
  other:['內建與外掛','分開看系統、同步內容與外掛，讓個人技能保持清楚。'],
  overlaps:['重疊檢查','了解相同與相近之處，再決定如何整理。'],
};
const state = {data:null, view:'personal', filter:'全部', query:'', selected:null, tab:'guide', sort:'name',
  content:new Map(), drafts:new Map(), busy:new Set(), theme:localStorage.getItem('skillpane-theme') || 'system'};
let toastTimer;

function hydrateIcons(root=document) {
  root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });
}
hydrateIcons();

function setTheme(theme) {
  state.theme = ['system','light','dark'].includes(theme) ? theme : 'system';
  localStorage.setItem('skillpane-theme', state.theme);
  const dark = state.theme === 'dark' || state.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $('#themeButton').innerHTML = icon(dark ? 'moon' : 'sun');
  $('#themeSelect').value = state.theme;
}
setTheme(state.theme);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => setTheme(state.theme));

function toast(message) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 2700);
}

async function api(url, options={}) {
  const response = await fetch(url, {
    ...options, headers:{'Content-Type':'application/json','X-Skillpane-Client':'1',...options.headers},
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || '操作未完成，請稍後再試。');
  return payload;
}

function annotations(skill) { return state.data.annotations[skill.id] || {}; }
function needsReview(skill) { return skill.warnings.length > 0 || ['review','merge','archive'].includes(annotations(skill).status); }
function categoryIcon(skill) { return ({'設計與動畫':'spark','維運與資料':'database','文件與簡報':'file','開發工具':'code'})[skill.category] || 'grid'; }
function displayedTime(iso) { return new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(iso)); }

function renderSummary() {
  const {stats,skills,overlaps} = state.data;
  $('#personalCount').textContent = stats.personal;
  $('#otherCount').textContent = stats.system + stats.managed + stats.plugin;
  $('#overlapCount').textContent = overlaps.length;
  $('#otherHint').textContent = stats.extra_versions ? `已收合 ${stats.extra_versions} 份額外快取版本` : '系統、同步內容與外掛';
  const counts = {personal:stats.personal, other:stats.system+stats.managed+stats.plugin,
    favorites:skills.filter(s => annotations(s).favorite).length,
    review:skills.filter(needsReview).length, overlaps:overlaps.length};
  Object.entries(counts).forEach(([key,value]) => document.querySelectorAll(`[data-count="${key}"]`).forEach(el => { el.textContent=value; }));
  $('#scanTime').textContent = `掃描於 ${displayedTime(state.data.generated_at)} · 台灣時間`;
}

function baseSkills() {
  const all = state.data?.skills || [];
  if (state.view === 'personal') return all.filter(s => s.source === 'personal');
  if (state.view === 'other') return all.filter(s => s.source !== 'personal');
  if (state.view === 'favorites') return all.filter(s => annotations(s).favorite);
  if (state.view === 'review') return all.filter(needsReview);
  return all;
}

function matches(skill) {
  if (state.filter !== '全部') {
    const label = state.view === 'other' ? skill.source_label : skill.category;
    if (label !== state.filter) return false;
  }
  if (!state.query) return true;
  return [skill.name,skill.display_name,skill.summary,skill.description,skill.source_label,skill.category,skill.plugin,annotations(skill).note || ''].join(' ').toLowerCase().includes(state.query);
}

function filteredSkills() {
  return baseSkills().filter(matches).sort((a,b) => state.sort === 'modified'
    ? b.modified_at.localeCompare(a.modified_at)
    : a.display_name.localeCompare(b.display_name,'zh-Hant'));
}

function renderFilters() {
  const labels = state.view === 'overlaps' ? ['全部'] : ['全部',...new Set(baseSkills().map(s => state.view==='other' ? s.source_label : s.category))];
  if (!labels.includes(state.filter)) state.filter='全部';
  $('#filters').innerHTML = labels.map(label => `<button class="chip ${label===state.filter?'selected':''}" data-filter="${escape(label)}" aria-pressed="${label===state.filter}">${escape(label)}</button>`).join('');
}

function rowHtml(skill) {
  const saved=annotations(skill);
  return `<div role="listitem"><button class="skill-row ${skill.id===state.selected?'selected':''}" data-skill="${skill.id}" aria-pressed="${skill.id===state.selected}"><span class="skill-symbol">${icon(categoryIcon(skill))}</span><span class="row-body"><span class="row-title">${escape(skill.display_name)}${saved.favorite?`<span class="row-star">${icon('star')}</span>`:''}${skill.warnings.length?'<span class="warning-dot" title="有設定待確認"></span>':''}</span><span class="row-name">${escape(skill.name)}</span><span class="row-summary">${escape(skill.summary)}</span><span class="row-meta"><span>${escape(skill.source==='personal'?skill.category:skill.source_label)}</span>${saved.status && saved.status!=='keep'?`<i class="mini-dot"></i><span>${statusLabels[saved.status]}</span>`:''}${skill.versions.length>1?`<i class="mini-dot"></i><span>${skill.versions.length} 份快取</span>`:''}</span></span></button></div>`;
}

function renderList() {
  if (!state.data) return;
  if (state.view==='overlaps') {
    const groups=state.data.overlaps.map(group=>({...group,skills:group.ids.map(id=>state.data.skills.find(s=>s.id===id)).filter(s=>s && matches(s))})).filter(g=>g.skills.length);
    $('#listCount').textContent=`${groups.length} 組檢查候選`;
    $('#skillList').innerHTML=groups.map(g=>`<section class="overlap-group"><h3>${escape(g.title)} · ${escape(g.label)}</h3><p>${escape(g.reason)}</p>${g.skills.map(rowHtml).join('')}</section>`).join('') || emptyHtml('沒有符合條件的檢查候選');
    $('#listFootnote').textContent='檢查候選需要人工確認；用途相近不代表可以刪除。';
  } else {
    const skills=filteredSkills();
    $('#listCount').textContent=`${skills.length} 個技能`;
    $('#skillList').innerHTML=skills.map(rowHtml).join('') || emptyHtml(state.view==='favorites'?'還沒有收藏的技能':'沒有符合條件的技能');
    $('#listFootnote').textContent=state.view==='other'?'快取不代表已啟用；不同版本已收合顯示。':'共用連結合併顯示，不重複計數。';
  }
}

function emptyHtml(title) { return `<div class="empty-list">${icon('search')}<strong>${escape(title)}</strong>試著調整搜尋或篩選條件。</div>`; }

function setView(view) {
  if (!views[view] || !state.data) return;
  state.view=view;state.filter='全部';state.query='';state.selected=null;state.tab='guide';
  $('#searchInput').value='';
  $('#pageTitle').textContent=views[view][0];
  $('#pageDescription').textContent=views[view][1];
  $('#breadcrumbName').textContent=views[view][0];
  document.querySelectorAll('.nav-item').forEach(el=>{
    el.classList.toggle('active',el.dataset.view===view);
    if(el.dataset.view===view)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');
  });
  renderFilters();renderList();
  const first=state.view==='overlaps' ? state.data.overlaps[0]?.ids[0] : filteredSkills()[0]?.id;
  if(first) selectSkill(first);else renderEmptyDetail();
}

function selectSkill(id) {
  state.selected=id;state.tab='guide';
  renderList();renderDetail();
}

function renderEmptyDetail() {
  $('#detailPane').innerHTML=`<div class="detail-empty">${icon('grid')}<h2>留一點空間，給剛好需要的技能</h2><p>搜尋技能，或從其他分類開始探索。</p></div>`;
}

function renderDetail() {
  const skill=state.data.skills.find(s=>s.id===state.selected);
  if(!skill){renderEmptyDetail();return;}
  const saved=annotations(skill);
  $('#detailPane').innerHTML=`<div class="detail-head"><div class="detail-topline"><span class="source-pill">${escape(skill.source_label)}</span><button class="icon-button ${saved.favorite?'is-favorite':''}" id="favoriteButton" aria-label="${saved.favorite?'取消收藏':'收藏這個技能'}" aria-pressed="${Boolean(saved.favorite)}">${icon('star')}</button></div><div class="detail-identity"><span class="detail-symbol">${icon(categoryIcon(skill))}</span><div><h2>${escape(skill.display_name)}</h2><div class="detail-code-name">${escape(skill.name)}</div></div></div><p class="detail-summary">${escape(skill.summary)}</p><div class="detail-tags"><span class="tool-pill">${icon('grid')}${escape(skill.category)}</span>${skill.associated_tools.map(tool=>`<span class="tool-pill">${escape(tool)} 目錄</span>`).join('')}<span class="tool-pill">${icon('lock')}原始檔唯讀</span></div><div class="detail-tabs" role="tablist" aria-label="技能資訊">${[['guide','使用指南'],['raw','原始內容'],['source','來源與設定']].map(([key,label])=>`<button role="tab" id="tab-${key}" aria-controls="tabContent" aria-selected="${state.tab===key}" class="detail-tab ${state.tab===key?'selected':''}" data-tab="${key}">${label}</button>`).join('')}</div></div><div class="detail-content" id="tabContent" role="tabpanel" aria-labelledby="tab-${state.tab}">${state.tab==='guide'?guideHtml(skill):state.tab==='source'?sourceHtml(skill):'<div class="loading-state">正在讀取原始內容…</div>'}</div>`;
  if(state.tab==='raw') loadRaw(skill);
}

function commandRow(host,command) {
  return `<div class="command-row"><span class="command-host">${host}</span><code>${escape(command || '請使用技能選擇器')}</code>${command?`<button class="copy-button" data-copy="${escape(command)}" aria-label="複製 ${host} 呼叫指令">${icon('copy')}</button>`:''}</div>`;
}

function guideHtml(skill) {
  const saved=annotations(skill);
  const note=state.drafts.has(skill.id)?state.drafts.get(skill.id):saved.note || '';
  return `<section class="detail-section"><h3 class="section-heading">如何呼叫</h3><div class="command-card">${commandRow('Codex CLI',skill.commands.codex)}${commandRow('Claude Code',skill.commands.claude)}</div><p class="helper-text">以上為 CLI 呼叫格式；桌面版也可使用技能選擇器，或在指令中明確指定技能名稱。目錄關聯不代表目前對話已載入。</p></section><section class="detail-section"><h3 class="section-heading">試著這樣說<span class="muted">可直接複製</span></h3><div class="prompt-card"><p>${escape(skill.example)}</p><button class="copy-button" data-copy="${escape(skill.example)}" aria-label="複製使用範例">${icon('copy')}</button></div></section>${skill.warnings.map(w=>`<div class="notice">${icon('info')}${escape(w)}</div>`).join('')}<section class="detail-section"><div class="organize-head"><h3 class="section-heading">我的整理</h3><select class="organize-select" id="statusSelect" aria-label="整理狀態">${Object.entries(statusLabels).map(([key,label])=>`<option value="${key}" ${(saved.status||'keep')===key?'selected':''}>${label}</option>`).join('')}</select></div><textarea class="note-input" id="noteInput" placeholder="記下你會在什麼情境使用它…" aria-label="個人使用筆記" maxlength="4000">${escape(note)}</textarea><div class="note-footer"><span id="noteState">${state.drafts.has(skill.id)?'有尚未儲存的筆記':'只儲存在這台電腦，不修改技能內容'}</span><button class="secondary-button" id="saveNoteButton">儲存筆記</button></div></section><section class="detail-section"><h3 class="section-heading">使用紀錄</h3><p class="section-copy">尚未收集可靠的呼叫紀錄。</p><p class="helper-text">技能修改時間不等於使用時間，不會據此判定是否應該淘汰。</p></section>`;
}

function sourceHtml(skill) {
  return `<section class="detail-section"><h3 class="section-heading">技能本體</h3><div class="path-box">${escape(skill.path)}</div><p class="helper-text">原始檔維持唯讀；修改與封存功能尚未開放。</p></section>${skill.aliases.length>1?`<section class="detail-section"><h3 class="section-heading">共用連結<span class="muted">同一份本體，只計算一次</span></h3>${skill.aliases.filter(a=>a!==skill.path).map(a=>`<div class="version-item"><code>${escape(a)}</code></div>`).join('')}</section>`:''}<section class="detail-section"><h3 class="section-heading">自動選用設定</h3><div class="status-line"><span>Codex</span><span class="status-value">${skill.invocation.codex_implicit?'允許自動選用（明確設定或預設值）':'僅手動呼叫'}</span></div><div class="status-line"><span>Claude Code</span><span class="status-value">${skill.invocation.claude_implicit?'允許自動選用（明確設定或預設值）':'僅手動呼叫'}</span></div><p class="helper-text">依 SKILL.md 與 agents/openai.yaml 的宣告判讀；實際是否可呼叫仍取決於工具載入與專案設定。</p>${skill.warnings.map(w=>`<div class="notice">${escape(w)}</div>`).join('')}</section>${skill.source==='plugin'?`<section class="detail-section"><h3 class="section-heading">磁碟上的快取<span class="muted">${skill.versions.length} 份</span></h3><p class="helper-text">預設顯示版本排序較新的快取，並非已確認啟用的版本。</p>${skill.versions.map(v=>`<div class="version-item">${escape(v.version || '未標示版本')}<code>${escape(v.path)}</code></div>`).join('')}</section>`:''}<section class="detail-section"><h3 class="section-heading">檔案資訊</h3><div class="status-line"><span>最後修改</span><span>${escape(displayedTime(skill.modified_at))}<br>台灣時間 UTC+8</span></div><div class="status-line"><span>最近呼叫</span><span class="status-unknown">未知</span></div><div class="status-line"><span>內容指紋</span><code>${escape(skill.sha256.slice(0,16))}…</code></div></section>`;
}

async function loadRaw(skill) {
  try {
    let content=state.content.get(skill.id);
    if(content===undefined){content=(await api(`/api/skill?id=${skill.id}`)).content;state.content.set(skill.id,content);}
    if(state.selected!==skill.id || state.tab!=='raw') return;
    const pre=document.createElement('pre');pre.className='raw-content';pre.textContent=content;
    $('#tabContent').replaceChildren(pre);
  } catch(error) { if(state.selected===skill.id && state.tab==='raw') $('#tabContent').textContent=error.message; }
}

async function saveAnnotation(skillId,patch,successMessage) {
  if(state.busy.has(skillId)){toast('上一筆整理資料仍在儲存，請稍候。');return false;}
  state.busy.add(skillId);
  try {
    const annotation=await api(`/api/annotation?id=${skillId}`,{method:'PATCH',body:JSON.stringify(patch)});
    state.data.annotations[skillId]=annotation;
    renderSummary();renderList();
    if(successMessage)toast(successMessage);
    return true;
  } catch(error){toast(error.message);return false;}
  finally{state.busy.delete(skillId);}
}

async function refresh() {
  const button=$('#refreshButton');button.disabled=true;
  const initial=!state.data;
  if(!initial)$('#scanTime').textContent='正在重新掃描…';
  try {
    const data=await api(initial?'/api/state':'/api/rescan',initial?{}:{method:'POST',body:'{}'});
    state.data=data;state.content.clear();
    renderSummary();renderFilters();renderList();
    if(initial)setView('personal');
    else if(data.skills.some(s=>s.id===state.selected))renderDetail();else{state.selected=null;renderEmptyDetail();}
    if(!initial)toast('技能庫已更新');
  } catch(error){
    toast(error.message);
    if(initial){$('#skillList').innerHTML=emptyHtml('暫時無法讀取技能庫');$('#scanTime').textContent='請確認本機服務後重新掃描';}
    else renderSummary();
  } finally {button.disabled=false;}
}

document.addEventListener('click', async event=>{
  const target=event.target.closest('button');if(!target)return;
  if(target.dataset.view){setView(target.dataset.view);return;}
  if(target.dataset.skill){selectSkill(target.dataset.skill);return;}
  if(target.dataset.filter){state.filter=target.dataset.filter;renderFilters();renderList();return;}
  if(target.dataset.tab){state.tab=target.dataset.tab;renderDetail();return;}
  if(target.dataset.copy){
    try{await navigator.clipboard.writeText(target.dataset.copy);toast('已複製');}catch{toast('瀏覽器未允許複製，請手動選取文字。');}
    return;
  }
  if(target.id==='favoriteButton'){
    const skillId=state.selected;
    const skill=state.data.skills.find(s=>s.id===skillId);
    if(await saveAnnotation(skillId,{favorite:!annotations(skill).favorite},annotations(skill).favorite?'已取消收藏':'已加入收藏')){
      if(state.selected===skillId)renderDetail();
    }
  }
  if(target.id==='saveNoteButton'){
    const skillId=state.selected, note=$('#noteInput').value;
    target.disabled=true;
    if(await saveAnnotation(skillId,{note},'筆記已儲存在這台電腦')){
      if(state.drafts.get(skillId)===note)state.drafts.delete(skillId);
      if(state.selected===skillId && state.tab==='guide')$('#noteState').textContent=state.drafts.has(skillId)?'有尚未儲存的筆記':'筆記已儲存';
    }
    if(target.isConnected)target.disabled=false;
  }
});
$('#searchInput').addEventListener('input',event=>{state.query=event.target.value.trim().toLowerCase();renderList();});
$('#sortButton').addEventListener('click',()=>{state.sort=state.sort==='name'?'modified':'name';$('#sortButton').innerHTML=icon('sort')+`<span>${state.sort==='name'?'名稱':'修改時間'}</span>`;renderList();});
$('#detailPane').addEventListener('input',event=>{if(event.target.id==='noteInput'){state.drafts.set(state.selected,event.target.value);$('#noteState').textContent='有尚未儲存的筆記';}});
$('#detailPane').addEventListener('change',async event=>{
  if(event.target.id==='statusSelect'){
    const skillId=state.selected;event.target.disabled=true;
    const ok=await saveAnnotation(skillId,{status:event.target.value},'整理狀態已更新');
    if(event.target.isConnected){event.target.disabled=false;if(!ok)event.target.value=annotations(state.data.skills.find(s=>s.id===skillId)).status || 'keep';}
  }
});
$('#refreshButton').addEventListener('click',refresh);
$('#themeButton').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('#themeSelect').addEventListener('change',event=>setTheme(event.target.value));
$('#settingsButton').addEventListener('click',()=>$('#settingsDialog').showModal());
$('#closeSettings').addEventListener('click',()=>$('#settingsDialog').close());
$('#settingsDialog').addEventListener('click',event=>{if(event.target===$('#settingsDialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
$('#exportButton').addEventListener('click',async()=>{
  try{const data=await api('/api/export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download='skillpane-catalog.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('清單已匯出');}catch(error){toast(error.message);}
});
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('#searchInput').focus();$('#searchInput').select();}
  if(event.key==='Escape' && document.activeElement===$('#searchInput')){state.query='';$('#searchInput').value='';renderList();}
});
window.addEventListener('beforeunload',event=>{if(state.drafts.size){event.preventDefault();event.returnValue='';}});
if(/Mac|iPhone|iPad/.test(navigator.platform))$('#searchShortcut').textContent='⌘ K';
await refresh();
