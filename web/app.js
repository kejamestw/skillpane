import {customize, organizationHtml, historyHtml, loadSourceEvidence, initializeManagement} from './management.js';
import {promptsHtml, initializePrompts} from './prompts.js';
import {initializeChanges, renderChanges} from './changes.js';

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
  sidebar:'M3 4h18v16H3z M9 4v16 M5.5 8h1 M5.5 12h1',
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
  overlaps:['重疊檢查','比較同名或內容相同的技能。'],
  related:['相關工具','依分類查看工具分工，不代表重複或需要淘汰。'],
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

function setTextSize(value){
  const size=['standard','large','extra-large'].includes(value)?value:'standard';
  document.documentElement.dataset.textSize=size;
  localStorage.setItem('skillpane-text-size',size);$('#textSizeSelect').value=size;
}
function setSidebar(hidden){
  $('.app-shell').classList.toggle('sidebar-hidden',hidden);
  const button=$('#sidebarToggle'),label=hidden?'顯示側邊欄':'隱藏側邊欄';
  button.setAttribute('aria-expanded',String(!hidden));button.setAttribute('aria-label',label);button.title=label;
  localStorage.setItem('skillpane-sidebar-hidden',hidden?'1':'0');
}
setTextSize(localStorage.getItem('skillpane-text-size'));
setSidebar(localStorage.getItem('skillpane-sidebar-hidden')==='1');

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
  if (!response.ok) {const error=new Error(payload.error || '操作未完成，請稍後再試。');error.status=response.status;throw error;}
  return payload;
}

function allSkills() { return (state.data?.skills || []).map(skill=>customize(skill,state.data.annotations[skill.id] || {})); }
function annotations(skill) { return state.data.annotations[skill.id] || {}; }
function needsReview(skill) { return skill.warnings.length > 0 || ['review','merge','archive'].includes(annotations(skill).status); }
function categoryIcon(skill) { return ({'設計與動畫':'spark','維運與資料':'database','文件與簡報':'file','開發工具':'code'})[skill.category] || 'grid'; }
function displayedTime(iso) { return new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(iso)); }

function renderSummary() {
  const {stats,skills,overlaps,related_groups} = state.data;
  $('#storageAlert').hidden=!state.data.storage_error;
  $('#storageAlertText').textContent=state.data.storage_error || '';
  $('#compareButton').disabled=skills.length<2;
  $('#personalCount').textContent = stats.personal;
  $('#otherCount').textContent = stats.system + stats.managed + stats.plugin;
  $('#overlapCount').textContent = overlaps.length;
  $('#otherSummary').title = stats.extra_versions ? `已收合 ${stats.extra_versions} 份額外快取版本` : '系統、同步內容與外掛';
  const counts = {personal:stats.personal, other:stats.system+stats.managed+stats.plugin,
    favorites:skills.filter(s => annotations(s).favorite).length,
    review:skills.filter(needsReview).length, overlaps:overlaps.length, related:related_groups.length};
  Object.entries(counts).forEach(([key,value]) => document.querySelectorAll(`[data-count="${key}"]`).forEach(el => { el.textContent=value; }));
  $('#scopeRoots').replaceChildren(...state.data.scan_scope.roots.map(path=>{const li=document.createElement('li');li.textContent=path;return li;}));
  $('#scanTime').textContent = `掃描於 ${displayedTime(state.data.generated_at)} · 台灣時間`;
  renderChanges();
}

function baseSkills() {
  const all = allSkills();
  if (['personal','related'].includes(state.view)) return all.filter(s => s.source === 'personal');
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
  return [skill.name,skill.display_name,skill.summary,skill.description,skill.source_label,skill.category,skill.plugin,annotations(skill).note || '',...(annotations(skill).tags || []),annotations(skill).origin_reason || '',annotations(skill).scope_note || '',...(annotations(skill).prompts || []).flatMap(prompt=>[prompt.title,prompt.body])].join(' ').toLowerCase().includes(state.query);
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

function visibleGroups() {
  const groups=state.view==='related' ? state.data.related_groups : state.data.overlaps;
  const byId=new Map(allSkills().map(skill=>[skill.id,skill]));
  return groups.map(group=>({...group,skills:group.ids.map(id=>byId.get(id)).filter(s=>s && matches(s))})).filter(group=>group.skills.length);
}

function visibleSkills() {
  if(!['overlaps','related'].includes(state.view)) return filteredSkills();
  return [...new Map(visibleGroups().flatMap(group=>group.skills).map(skill=>[skill.id,skill])).values()];
}

function renderList() {
  if (!state.data) return;
  if (['overlaps','related'].includes(state.view)) {
    const groups=visibleGroups();
    $('#listCount').textContent=`${groups.length} 組${state.view==='related'?'相關工具':'檢查候選'}`;
    $('#skillList').innerHTML=groups.map(group=>`<section class="overlap-group"><h3>${escape(group.title)} · ${escape(group.label)}</h3><p>${escape(group.reason)}</p>${group.skills.length>1?`<button class="quiet-button compact group-compare" data-compare-left="${group.skills[0].id}" data-compare-right="${group.skills[1].id}">${icon('intersect')}比較前兩項${state.data.comparisons[[group.skills[0].id,group.skills[1].id].sort().join(':')]?` · ${state.data.comparisons[[group.skills[0].id,group.skills[1].id].sort().join(':')].needs_review?'內容已變動':'已有結論'}`:''}</button>`:''}${group.skills.map(rowHtml).join('')}</section>`).join('') || emptyHtml('沒有符合條件的項目');
    $('#listFootnote').textContent=state.view==='related'?'僅依分類整理，不是重複或淘汰判定。':'同名與相同內容分開比較，不會自動合併或刪除。';
  } else {
    const skills=filteredSkills();
    $('#listCount').textContent=`${skills.length} 個技能`;
    $('#skillList').innerHTML=skills.map(rowHtml).join('') || emptyHtml(state.view==='favorites'?'還沒有收藏的技能':'沒有符合條件的技能');
    $('#listFootnote').textContent=state.view==='other'?'快取不代表已啟用；不同版本已收合顯示。':'共用連結合併顯示，不重複計數。';
  }
  syncRowTabStops();
}

// A long list is a single Tab stop (the selected row); arrow keys move within it.
function syncRowTabStops() {
  const rows=[...document.querySelectorAll('#skillList .skill-row')];
  const current=rows.find(row=>row.dataset.skill===state.selected) || rows[0];
  rows.forEach(row=>{row.tabIndex=row===current?0:-1;});
}

function updateResults({resetScroll=false,renderSelected=false}={}) {
  const list=$('#skillList'), position=list.scrollTop;
  const visible=visibleSkills();
  const selected=visible.some(skill=>skill.id===state.selected) ? state.selected : visible[0]?.id || null;
  const changed=selected!==state.selected;
  state.selected=selected;
  if(changed)state.tab='guide';
  renderList();
  list.scrollTop=resetScroll?0:position;
  if(changed || renderSelected || !selected)renderDetail();
}

function emptyHtml(title) { return `<div class="empty-list">${icon('search')}<strong>${escape(title)}</strong>試著調整搜尋或篩選條件。</div>`; }

function setView(view) {
  if (!views[view] || !state.data) return;
  state.view=view;state.filter='全部';state.query='';state.selected=null;state.tab='guide';
  $('#searchInput').value='';
  $('#pageTitle').textContent=views[view][0];
  document.querySelectorAll('.nav-item').forEach(el=>{
    el.classList.toggle('active',el.dataset.view===view);
    if(el.dataset.view===view)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');
  });
  renderFilters();updateResults({resetScroll:true,renderSelected:true});
}

function selectSkill(id) {
  if(!visibleSkills().some(skill=>skill.id===id))return;
  state.selected=id;state.tab='guide';
  // Selecting a row must not rebuild the list or disturb its scroll position.
  document.querySelectorAll('.skill-row').forEach(row=>{
    const selected=row.dataset.skill===id;
    row.classList.toggle('selected',selected);
    row.setAttribute('aria-pressed',String(selected));
  });
  syncRowTabStops();
  renderDetail();
}

function renderEmptyDetail() {
  $('#detailPane').innerHTML=`<div class="detail-empty">${icon('grid')}<h2>留一點空間，給剛好需要的技能</h2><p>搜尋技能，或從其他分類開始探索。</p></div>`;
}

function renderDetail() {
  const skill=allSkills().find(s=>s.id===state.selected);
  if(!skill){renderEmptyDetail();return;}
  const saved=annotations(skill);
  $('#detailPane').innerHTML=`<div class="detail-head"><div class="detail-identity"><span class="detail-symbol">${icon(categoryIcon(skill))}</span><div class="detail-name"><h2>${escape(skill.display_name)}</h2><div class="detail-code-name">${escape(skill.name)}${skill.provenance.display_name==='user'?'<span class="origin-label">我的自訂名稱</span>':skill.provenance.display_name==='skillpane'?'<span class="origin-label">Skillpane 中文別名</span>':''}</div></div><button class="icon-button ${saved.favorite?'is-favorite':''}" id="favoriteButton" aria-label="${saved.favorite?'取消收藏':'收藏這個技能'}" aria-pressed="${Boolean(saved.favorite)}">${icon('star')}</button></div><p class="detail-summary" title="${escape(skill.summary)}">${escape(skill.summary)}</p><div class="detail-tabs" role="tablist" aria-label="技能資訊">${[['guide','使用指南'],['raw','原始內容'],['source','來源與設定']].map(([key,label])=>`<button role="tab" id="tab-${key}" aria-controls="tabContent" aria-selected="${state.tab===key}" class="detail-tab ${state.tab===key?'selected':''}" data-tab="${key}">${label}</button>`).join('')}</div></div><div class="detail-content" id="tabContent" role="tabpanel" tabindex="0" aria-labelledby="tab-${state.tab}">${state.tab==='guide'?guideHtml(skill):state.tab==='source'?sourceHtml(skill):'<div class="loading-state">正在讀取原始內容…</div>'}</div>`;
  if(state.tab==='raw') loadRaw(skill);
  if(state.tab==='source') loadSourceEvidence(skill.id);
}

function commandRow(host,command) {
  return `<div class="command-row"><span class="command-host">${host}</span><code>${escape(command || '請在對應工具的技能選擇器確認')}</code>${command?`<button class="copy-button" data-copy="${escape(command)}" aria-label="複製 ${host} 呼叫指令">${icon('copy')}</button>`:''}</div>`;
}

function diagnosticsHtml(skill) {
  return skill.warnings.map(w=>`<div class="notice">${icon('info')}${escape(w)}</div>`).join('') +
    skill.advisories.map(w=>`<div class="advisory">${icon('info')}${escape(w)}</div>`).join('');
}

function guideHtml(skill) {
  const saved=annotations(skill);
  const note=state.drafts.has(skill.id)?state.drafts.get(skill.id):saved.note || '';
  return `<section class="detail-section">
    <h3 class="section-heading">呼叫方式<span class="muted">CLI 參考格式</span></h3>
    <div class="command-card">${commandRow('Codex CLI',skill.commands.codex)}${commandRow('Claude Code',skill.commands.claude)}</div>
    <details class="call-help"><summary>呼叫方式說明</summary><p class="helper-text">${escape(skill.command_note)} 桌面版可透過技能選擇器或明確指定技能名稱。目錄關聯不代表目前對話已載入。</p></details>
  </section><section class="detail-section">
    <h3 class="section-heading">試著這樣說<span class="muted">Skillpane 示範</span></h3>
    <div class="prompt-card"><p>${escape(skill.example)}</p><button class="copy-button" data-copy="${escape(skill.example)}" aria-label="複製使用範例">${icon('copy')}</button></div>
    <button id="saveExamplePrompt" class="quiet-button compact">另存為我的提示詞</button>
  </section>${promptsHtml(skill,saved,icon)}${diagnosticsHtml(skill)}<section class="detail-section">
    <div class="organize-head"><h3 class="section-heading">我的整理</h3><button id="editMetadataButton" class="quiet-button compact">編輯整理資訊</button><select class="organize-select" id="statusSelect" aria-label="整理狀態">${Object.entries(statusLabels).map(([key,label])=>`<option value="${key}" ${(saved.status||'keep')===key?'selected':''}>${label}</option>`).join('')}</select></div>
    ${organizationHtml(skill,saved)}<p class="helper-text note-help">記錄使用時機與心得；常用的完整說法可存到上方「常用提示詞」。</p><textarea class="note-input" id="noteInput" placeholder="記下你會在什麼情境使用它…" aria-label="個人使用筆記" maxlength="4000">${escape(note)}</textarea>
    <div class="note-footer"><span id="noteState">${state.drafts.has(skill.id)?'有尚未儲存的筆記':'只儲存在這台電腦，不修改技能內容'}</span><button class="secondary-button" id="saveNoteButton">儲存筆記</button></div>
  </section>`;
}

function settingHtml(host,setting) {
  const label=setting.state==='unknown'?'無法判讀':`${setting.allowed?'允許':'禁止'}自動選用（${setting.state==='explicit'?'明確設定':'採工具預設'}）`;
  return `<div class="policy-card"><div class="status-line"><span>${host}</span><span class="${setting.state==='unknown'?'status-unknown':'status-value'}">${label}</span></div><code>${escape(setting.source)}${setting.line?`:${setting.line}`:''}</code><p class="helper-text">欄位：${escape(setting.field)} · ${escape(setting.reason)}</p></div>`;
}

function sourceHtml(skill) {
  return `<section class="detail-section">
    <h3 class="section-heading">內容來源</h3>
    <div class="status-line"><span>顯示名稱</span><span>${skill.provenance.display_name==='user'?'使用者自訂名稱':skill.provenance.display_name==='skillpane'?'Skillpane 中文別名':skill.provenance.display_name==='folder'?'資料夾名稱（原始名稱缺漏或無法判讀）':'技能原始名稱'}</span></div>
    <div class="status-line"><span>用途摘要</span><span>${skill.provenance.summary==='user'?'使用者自訂摘要':skill.provenance.summary==='skillpane'?'Skillpane 補充摘要':skill.provenance.summary==='fallback'?'缺少原始描述，使用面板提示':'原始 description'}</span></div>
    <div class="status-line"><span>使用範例</span><span>Skillpane 示範，非原作者指令</span></div>
    <h3 class="section-heading original-heading">原始描述</h3><p class="section-copy original-description">${escape(skill.description || '原始檔未提供 description。')}</p>
    <div class="detail-tags"><span class="tool-pill">${escape(skill.source_label)}</span><span class="tool-pill">${escape(skill.category)}</span>${skill.associated_tools.map(tool=>`<span class="tool-pill">${escape(tool)} 目錄</span>`).join('')}</div>
  </section>${historyHtml(skill,annotations(skill),displayedTime)}<section class="detail-section">
    <h3 class="section-heading">技能本體</h3><div class="path-box">${escape(skill.path)}</div><p class="helper-text">原始檔維持唯讀；整理標記不會停用或封存技能。</p>
  </section>${skill.aliases.length>1?`<section class="detail-section"><h3 class="section-heading">共用連結<span class="muted">同一份本體，只計算一次</span></h3>${skill.aliases.filter(a=>a!==skill.path).map(a=>`<div class="version-item"><code>${escape(a)}</code></div>`).join('')}</section>`:''}
  <section class="detail-section"><h3 class="section-heading">自動選用宣告</h3>
    ${settingHtml('Codex',skill.invocation.codex)}${settingHtml('Claude Code',skill.invocation.claude)}
    <p class="helper-text">僅判讀相關欄位，不是整份 YAML 的驗證或實際啟用確認。原文中的使用意圖與工具強制設定分開看；實際可用性仍取決於工具載入及專案設定。</p>${diagnosticsHtml(skill)}
  </section>${skill.source==='plugin'?`<section class="detail-section"><h3 class="section-heading">磁碟上的快取<span class="muted">${skill.versions.length} 份</span></h3><p class="helper-text">顯示版本排序較新的快取，實際啟用版本未知。${escape(skill.command_note)}</p>${skill.versions.map(v=>`<div class="version-item">${escape(v.version || '未標示版本')}<code>${escape(v.path)}</code></div>`).join('')}</section>`:''}
  <section class="detail-section"><h3 class="section-heading">檔案資訊</h3><div class="status-line"><span>最後修改</span><span>${escape(displayedTime(skill.modified_at))}<br>台灣時間 UTC+8</span></div><div class="status-line"><span>最近呼叫</span><span class="status-unknown">未知，修改時間不等於使用時間</span></div><div class="status-line"><span>內容指紋</span><code>${escape(skill.sha256.slice(0,16))}…</code></div></section>`;
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
    renderSummary();renderFilters();updateResults();
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
    renderSummary();
    if(initial)setView('personal');
    else{renderFilters();updateResults({renderSelected:true});}
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
  if(target.dataset.filter){state.filter=target.dataset.filter;renderFilters();updateResults({resetScroll:true});return;}
  if(target.dataset.tab){state.tab=target.dataset.tab;renderDetail();return;}
  if(target.dataset.copy){
    try{await navigator.clipboard.writeText(target.dataset.copy);toast('已複製');}catch{toast('瀏覽器未允許複製，請手動選取文字。');}
    return;
  }
  if(target.id==='favoriteButton'){
    const skillId=state.selected;
    const skill=allSkills().find(s=>s.id===skillId);
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
// IME composition text (e.g. Zhuyin symbols) is not a query yet; compositionend applies the result.
function applySearch(value){const query=value.trim().toLowerCase();if(query===state.query)return;state.query=query;updateResults({resetScroll:true});}
$('#searchInput').addEventListener('input',event=>{if(!event.isComposing)applySearch(event.target.value);});
$('#skillList').addEventListener('keydown',event=>{
  const row=event.target.closest('.skill-row');
  if(!row || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey)return;
  const rows=[...document.querySelectorAll('#skillList .skill-row')],index=rows.indexOf(row);
  const next={ArrowDown:index+1,ArrowUp:index-1,Home:0,End:rows.length-1}[event.key];
  if(next===undefined)return;
  event.preventDefault();
  const target=rows[Math.max(0,Math.min(rows.length-1,next))];
  selectSkill(target.dataset.skill);
  target.focus();
});
$('#searchInput').addEventListener('compositionend',event=>applySearch(event.target.value));
$('#sortButton').addEventListener('click',()=>{state.sort=state.sort==='name'?'modified':'name';$('#sortButton').innerHTML=icon('sort')+`<span>${state.sort==='name'?'名稱':'修改時間'}</span>`;updateResults({resetScroll:true});});
$('#detailPane').addEventListener('input',event=>{if(event.target.id==='noteInput'){const saved=state.data.annotations[state.selected]?.note || '';if(event.target.value===saved)state.drafts.delete(state.selected);else state.drafts.set(state.selected,event.target.value);$('#noteState').textContent=state.drafts.has(state.selected)?'有尚未儲存的筆記':'只儲存在這台電腦，不修改技能內容';}});
$('#detailPane').addEventListener('change',async event=>{
  if(event.target.id==='statusSelect'){
    const skillId=state.selected;event.target.disabled=true;
    const ok=await saveAnnotation(skillId,{status:event.target.value},'整理狀態已更新');
    if(event.target.isConnected){event.target.disabled=false;if(!ok)event.target.value=annotations(allSkills().find(s=>s.id===skillId)).status || 'keep';}
  }
});
$('#refreshButton').addEventListener('click',refresh);
$('#themeButton').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('#themeSelect').addEventListener('change',event=>setTheme(event.target.value));
$('#textSizeSelect').addEventListener('change',event=>setTextSize(event.target.value));
$('#sidebarToggle').addEventListener('click',()=>setSidebar(!$('.app-shell').classList.contains('sidebar-hidden')));
$('#quickSettingsButton').addEventListener('click',()=>$('#settingsDialog').showModal());
$('#scopeButton').addEventListener('click',()=>$('#scopeDialog').showModal());
$('#closeScope').addEventListener('click',()=>$('#scopeDialog').close());
$('#settingsButton').addEventListener('click',()=>$('#settingsDialog').showModal());
$('#closeSettings').addEventListener('click',()=>$('#settingsDialog').close());
$('#settingsDialog').addEventListener('click',event=>{if(event.target===$('#settingsDialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
$('#exportButton').addEventListener('click',async()=>{
  try{const data=await api('/api/export');const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download='skillpane-catalog.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('清單已匯出');}catch(error){toast(error.message);}
});
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('#searchInput').focus();$('#searchInput').select();}
  if(event.key==='Escape' && document.activeElement===$('#searchInput')){state.query='';$('#searchInput').value='';updateResults({resetScroll:true});}
});
window.addEventListener('beforeunload',event=>{if(state.drafts.size || state.managementDirty?.size){event.preventDefault();event.returnValue='';}});
if(/Mac|iPhone|iPad/.test(navigator.platform))$('#searchShortcut').textContent='⌘ K';
async function syncState(){state.data=await api('/api/state');renderSummary();renderFilters();updateResults({renderSelected:true});}
initializeManagement({state,api,syncState,toast,displayedTime});
initializePrompts({state,api,syncState,toast});
initializeChanges({state,displayedTime,refresh,openSkill(id){const skill=state.data.skills.find(item=>item.id===id);if(skill){setView(skill.source==='personal'?'personal':'other');selectSkill(id);}}});
await refresh();
