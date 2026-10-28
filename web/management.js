// Local organization UI. Skill source files remain read-only.
let context;
const $=selector=>document.querySelector(selector);
const esc=value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fields=['alias','summary','category','tags','origin_reason','source_url','scope_note','modifies_files','display_mode'];
const names={favorite:'收藏',status:'整理狀態',note:'筆記',alias:'名稱',summary:'摘要',category:'分類',tags:'標籤',origin_reason:'加入原因',source_url:'來源網址',scope_note:'工作範圍',modifies_files:'是否改檔',display_mode:'顯示方式'};
const decisions={'keep-both':'保留兩者，分工不同','consider-merge':'考慮合併','checked':'已檢查'};
const metaDrafts=new Map(), compareDrafts=new Map();
let editingId, importPreview, relinkPreview, cleanupPreview, compareRequest=0;

export function customize(skill, saved={}) {
  const original=saved.display_mode==='original';
  return {...skill,display_name:saved.alias?.trim() || (original?skill.name:skill.display_name),
    summary:saved.summary?.trim() || (original?skill.description || '未提供原始描述':skill.summary),
    category:saved.category?.trim() || skill.category,
    provenance:{...skill.provenance,display_name:saved.alias?.trim()?'user':original?'skill':skill.provenance.display_name,
      summary:saved.summary?.trim()?'user':original?'skill':skill.provenance.summary}};
}

export function organizationHtml(skill, saved) {
  const tags=(saved.tags || []).map(tag=>`<span class="tool-pill">${esc(tag)}</span>`).join('');
  return `${tags?`<div class="custom-tags" aria-label="自訂標籤">${tags}</div>`:''}${saved.origin_reason?`<p class="helper-text personal-reason">加入原因：${esc(saved.origin_reason)}</p>`:''}`;
}

export function historyHtml(skill, saved, time) {
  return `<section class="detail-section"><h3 class="section-heading">來源與時間紀錄</h3>
    <div class="status-line"><span>首次被 Skillpane 發現</span><span>${esc(time(skill.first_seen_at))}<br>台灣時間 UTC+8</span></div>
    <div class="status-line"><span>本機檔案建立</span><span>${skill.created_at?esc(time(skill.created_at))+' · 台灣時間':'未知（檔案系統未提供）'}</span></div>
    <div class="status-line"><span>Git 最早新增提交</span><span id="gitEvidence" data-git-id="${skill.id}">正在查詢本機 Git 紀錄…</span></div>
    <p class="helper-text">以上時間各自代表不同紀錄，皆不等於安裝時間。Git 顯示最早新增提交的作者時間。</p>
    <div class="status-line"><span>加入原因</span><span class="personal-reason">${esc(saved.origin_reason || '尚未記錄')}</span></div>
    <div class="status-line"><span>來源網址</span><span>${saved.source_url?`<a href="${esc(saved.source_url)}" target="_blank" rel="noopener noreferrer">${esc(saved.source_url)}</a>`:'未知，可自行補充'}</span></div>
    <button class="secondary-button" data-edit-metadata="${skill.id}">編輯整理資訊</button></section>`;
}

export async function loadSourceEvidence(id) {
  const target=$('#gitEvidence');
  if(!target || !context)return;
  try{
    const data=await context.api(`/api/source?id=${id}`);
    if(!target.isConnected || target.dataset.gitId!==id)return;
    target.textContent=data.state==='known'?`${context.displayedTime(data.first_added_at)} · 台灣時間 · ${data.commit.slice(0,8)}`:data.state==='not-tracked'?'未找到此檔案的新增提交':'未知（無可讀取的本機 Git 證據）';
  }catch{if(target.isConnected)target.textContent='未知，暫時無法讀取 Git 紀錄';}
}

const markup=`
<dialog id="metadataDialog" class="management-dialog" aria-labelledby="metadataTitle">
  <div class="dialog-head"><h2 id="metadataTitle">整理技能資訊</h2><button class="icon-button" data-close="metadataDialog" aria-label="關閉整理資訊">×</button></div>
  <p class="dialog-description">留下一眼能懂的名稱與用途。只存於 Skillpane，不改寫技能本體。</p>
  <form id="metadataForm" class="management-form">
    <div class="field-grid"><label>自訂名稱<input name="alias" maxlength="100" placeholder="留白使用預設名稱"></label><label>自訂分類<input name="category" maxlength="40" placeholder="留白使用原分類"></label></div>
    <label>自訂摘要<textarea name="summary" maxlength="600" rows="2" placeholder="留白使用預設摘要"></textarea></label>
    <label>標籤<input name="tags" maxlength="400" placeholder="以逗號分隔，例如：前端、常用"></label>
    <div class="inline-actions"><button type="button" class="quiet-button" data-reset-display="original">使用原始名稱與描述</button><button type="button" class="quiet-button" data-reset-display="default">恢復面板預設</button></div>
    <input type="hidden" name="display_mode" value="default">
    <details class="metadata-extra"><summary>來源與工作範圍</summary>
      <label>為什麼加入／保留<textarea name="origin_reason" maxlength="1000" rows="2" placeholder="例如：網站改版時加入，保留作為設計參考"></textarea></label>
      <label>來源網址<input name="source_url" type="url" maxlength="2048" placeholder="https://github.com/owner/project"></label>
      <p class="helper-text">填寫不含帳密或憑證的來源網址；沒有證據的安裝時間維持未知。</p>
      <label>工作範圍<textarea name="scope_note" maxlength="600" rows="2" placeholder="依你的理解記錄用途與分工"></textarea></label>
      <label>是否改動檔案<select name="modifies_files"><option value="unknown">未知／尚未確認</option><option value="yes">會修改檔案（我的紀錄）</option><option value="no">維持唯讀（我的紀錄）</option></select></label>
    </details>
    <div class="dialog-actions"><span id="metadataState" role="status"></span><button type="submit" class="primary-button" id="saveMetadataButton">儲存整理資訊</button></div>
  </form>
</dialog>
<dialog id="dataDialog" class="management-dialog data-dialog" aria-labelledby="dataTitle">
  <div class="dialog-head"><h2 id="dataTitle">資料與備份</h2><button class="icon-button" data-close="dataDialog" aria-label="關閉資料與備份">×</button></div>
  <p class="dialog-description">備份已儲存的收藏、筆記、自訂資訊與比較結論。不含技能原文與本機來源路徑；備份含個人筆記，請妥善保存。</p>
  <p id="dataError" class="notice" role="alert" hidden></p>
  <div class="inline-actions"><button id="downloadBackup" class="primary-button">下載整理資料備份</button><button id="chooseBackup" class="secondary-button">匯入備份…</button><input id="backupFile" type="file" accept="application/json,.json" hidden></div>
  <section id="importSection" class="transfer-section" hidden><h3>匯入預覽</h3><p id="importCounts" class="helper-text"></p><p class="helper-text">每筆選擇對應技能、保留未關聯或略過。可搜尋其他對應；略過技能的比較結論也不匯入。</p><div id="importRows" class="transfer-list"></div>
    <label class="stack-label">相同欄位的處理方式<select id="importMode"><option value="keep">保留目前欄位，只補入缺少資料</option><option value="replace">以備份內容取代所選技能的整理資料</option></select></label>
    <label class="check-label"><input type="checkbox" id="restoreSettings">一併還原備份保留設定</label>
    <div class="dialog-actions"><span class="helper-text">套用前會另存目前資料備份。</span><button id="applyImport" class="primary-button">套用匯入</button></div>
  </section>
  <details class="transfer-section" id="orphanSection"><summary>未關聯資料 <span id="orphanCount">0</span></summary><p class="helper-text">未找到原技能的整理資料仍保留。選擇目前的技能，先預覽再接回原筆記；有歧義時不會自動合併。</p><div id="orphanRows" class="transfer-list"></div><div id="relinkSection" hidden></div></details>
  <details class="transfer-section"><summary>本機備份與還原 <span id="backupCount"></span></summary><p class="helper-text">儲存、升級或匯入前保留的版本。還原會先顯示對應與衝突預覽。</p><div id="backupRows" class="transfer-list"></div></details>
  <details class="transfer-section"><summary>備份保留策略</summary><p class="helper-text">預設全部保留。修改設定不會自動刪除檔案；清理前會逐一列出，再由你確認。</p><div class="inline-actions"><label>本機備份<select id="keepBackups"></select></label><button id="saveBackupPolicy" class="secondary-button">儲存設定</button><button id="previewCleanup" class="secondary-button">預覽清理</button></div><div id="cleanupSection" hidden></div></details>
</dialog>
<dialog id="compareDialog" class="management-dialog compare-dialog" aria-labelledby="compareTitle">
  <div class="dialog-head"><h2 id="compareTitle">比較技能</h2><button class="icon-button" data-close="compareDialog" aria-label="關閉技能比較">×</button></div>
  <p class="dialog-description">並排看用途與分工，再留下你的結論。工作範圍及是否改檔採用個人紀錄，未記錄時維持未知。</p>
  <div class="compare-grid"><label class="stack-label">技能 A<select id="compareLeft"></select></label><label class="stack-label">技能 B<select id="compareRight"></select></label></div>
  <p id="compareState" class="helper-text" role="status"></p><div id="comparePanels" class="compare-grid"></div>
  <details class="transfer-section"><summary>原文差異</summary><p id="diffNote" class="helper-text"></p><pre id="compareDiff" class="compare-diff" tabindex="0"></pre></details>
  <form id="comparisonForm" class="management-form"><label>整理結論<select id="compareDecision"><option value="keep-both">保留兩者，分工不同</option><option value="consider-merge">考慮合併</option><option value="checked">已檢查</option></select></label><label>理由<textarea id="compareReason" maxlength="2000" rows="3" placeholder="記下分工或需要後續處理的原因"></textarea></label><div class="dialog-actions"><span id="comparisonSaved" class="helper-text"></span><button class="primary-button" id="saveComparison" type="submit">儲存比較結論</button></div></form>
</dialog>`;

function saved(id){return context.state.data.annotations[id] || {};}
function skills(){return context.state.data.skills.map(skill=>customize(skill,saved(skill.id)));}
function skillOptions(items, selected){return items.map(skill=>`<option value="${skill.id}" ${skill.id===selected?'selected':''}>${esc(skill.display_name || skill.name)} · ${esc(skill.source_label || skill.source)}${skill.live===false?'（未關聯）':''}</option>`).join('');}
function post(url,payload){return context.api(url,{method:'POST',body:JSON.stringify(payload)});}
function noDrafts(){if(context.state.drafts.size || context.state.managementDirty.size)throw new Error('請先儲存或還原尚未儲存的草稿，再套用資料。');}
function report(error){context.toast(error.message);if($('#dataDialog').open){$('#dataError').textContent=error.message;$('#dataError').hidden=false;}}
async function busy(button, action){if(button.disabled)return;button.disabled=true;try{await action();}catch(error){report(error);}finally{if(button.isConnected)button.disabled=false;}}

function metaValues(annotation){return Object.fromEntries(fields.map(field=>[field,field==='tags'?(annotation.tags || []).join('、'):annotation[field] || (field==='display_mode'?'default':field==='modifies_files'?'unknown':'')]));}
function readMeta(){const form=$('#metadataForm');return Object.fromEntries(fields.map(field=>[field,form.elements.namedItem(field).value]));}
function writeMeta(values){const form=$('#metadataForm');fields.forEach(field=>{form.elements.namedItem(field).value=values[field];});}
function trackMeta(){const value=readMeta(),changed=JSON.stringify(value)!==JSON.stringify(metaValues(saved(editingId)));if(changed){metaDrafts.set(editingId,value);context.state.managementDirty.add('metadata:'+editingId);}else{metaDrafts.delete(editingId);context.state.managementDirty.delete('metadata:'+editingId);}$('#metadataState').textContent=changed?'尚未儲存；關閉後保留草稿':'只儲存在本機';}
function openMetadata(id){if(!context.state.data.skills.some(s=>s.id===id))return;editingId=id;writeMeta(metaDrafts.get(id) || metaValues(saved(id)));const s=skills().find(s=>s.id===id);$('#metadataTitle').textContent='整理 '+s.display_name;$('#metadataForm [name=alias]').placeholder=s.name;$('#metadataDialog').showModal();trackMeta();}

async function openData(){if(!context.state.data)return;$('#dataError').hidden=!context.state.data.storage_error;$('#dataError').textContent=context.state.data.storage_error || '';$('#downloadBackup').disabled=Boolean(context.state.data.storage_error);if(!$('#dataDialog').open)$('#dataDialog').showModal();await renderData();}
async function renderData(){
  const data=await context.api('/api/backups');
  $('#backupCount').textContent=`（${data.files.length} 份）`;
  $('#backupRows').innerHTML=data.files.map(file=>`<div class="backup-row"><div><strong>${esc(context.displayedTime(file.modified_at))} · 台灣時間</strong><small>${esc(file.id)} · ${(file.size/1024).toFixed(1)} KiB</small></div><button class="secondary-button" data-restore="${esc(file.id)}">預覽還原</button></div>`).join('') || '<p class="helper-text">目前沒有較早的本機備份。</p>';
  const keep=data.settings.keep_last;
  const options=[...new Set([null,10,30,100,keep])];
  $('#keepBackups').innerHTML=options.map(value=>`<option value="${value===null?'all':value}" ${value===keep?'selected':''}>${value===null?'全部保留':`保留最近 ${value} 份`}</option>`).join('');
  const orphans=context.state.data.orphans;
  $('#orphanCount').textContent=orphans.length;
  $('#orphanRows').innerHTML=orphans.map(item=>`<div class="orphan-row"><div><strong>${esc(item.annotation.alias || item.identity.name)}</strong><p class="helper-text">${esc(item.annotation.note || item.annotation.origin_reason || '未附筆記')} · ${esc(item.identity.source)}</p></div><label class="stack-label">接到目前技能<select name="relink-${item.id}" data-relink-target="${item.id}"><option value="">請選擇對應技能</option>${skillOptions(skills())}</select></label><button class="secondary-button" data-relink-from="${item.id}">預覽關聯</button></div>`).join('') || '<p class="helper-text">目前沒有未關聯的資料。</p>';
}
function targetOptions(row, filter=''){
  const choice=payloadChoice(row.id) ?? row.target;
  const candidates=importPreview.targets.filter(target=>target.id===choice || (filter?[target.name,target.source].join(' ').toLowerCase().includes(filter.toLowerCase()):row.candidates.includes(target.id))).slice(0,80);
  return `<option value="" ${!choice?'selected':''}>請確認對應</option><option value="orphan" ${choice==='orphan'?'selected':''}>保留為未關聯資料</option><option value="skip" ${choice==='skip'?'selected':''}>略過這筆</option>${skillOptions(candidates,choice)}`;
}
function annotationView(value){
  if(!Object.keys(value).length)return '<p class="helper-text">尚無整理資訊</p>';
  const labels={status:{keep:'保留使用',review:'待檢查',merge:'考慮合併',archive:'考慮封存'},display_mode:{default:'面板預設',original:'原始名稱與描述'},modifies_files:{unknown:'未知',yes:'會修改檔案',no:'維持唯讀'}};
  return '<dl class="annotation-preview">'+Object.entries(value).map(([key,content])=>`<dt>${esc(names[key] || key)}</dt><dd>${esc(key==='favorite'?content?'已收藏':'未收藏':Array.isArray(content)?content.join('、'):labels[key]?.[content] || content || '（留白）')}</dd>`).join('')+'</dl>';
}
function payloadChoice(id){return $(`[data-import-choice="${id}"]`)?.value;}
function updateImportDiff(row){
  const target=payloadChoice(row.id),current=saved(target),conflicts=Object.keys(row.incoming).filter(key=>key in current && JSON.stringify(current[key])!==JSON.stringify(row.incoming[key]));
  const block=$(`[data-import-diff="${row.id}"]`);
  block.innerHTML=`<summary>${conflicts.length?`有 ${conflicts.length} 個衝突欄位：${conflicts.map(k=>esc(names[k] || k)).join('、')}`:'查看目前與備份內容'}</summary><div class="compare-grid"><div><h4>目前資料</h4>${annotationView(current)}</div><div><h4>備份內容</h4>${annotationView(row.incoming)}</div></div>`;
}
function updateImportCounts(){const choices=importPreview.rows.map(row=>payloadChoice(row.id));$('#importCounts').textContent=`共 ${choices.length} 筆：${choices.filter(v=>v && !['skip','orphan'].includes(v)).length} 筆對應、${choices.filter(v=>v==='orphan').length} 筆未關聯、${choices.filter(v=>v==='skip').length} 筆略過、${choices.filter(v=>!v).length} 筆待選擇；另含 ${importPreview.comparisons} 筆比較結論。`;$('#applyImport').disabled=choices.some(v=>!v);}
function showImport(data){
  importPreview=data;$('#importRows').replaceChildren();$('#importSection').hidden=false;$('#importRows').innerHTML=data.rows.map(row=>`<div class="import-row"><strong>${esc(row.name)} <span class="muted">${esc(row.source)}</span></strong><p class="helper-text">${esc(row.basis)}</p><div class="field-grid"><label>對應技能<select name="import-${row.id}" data-import-choice="${row.id}">${targetOptions(row)}</select></label><label>搜尋其他對應<input name="search-${row.id}" data-target-search="${row.id}" placeholder="輸入技能名稱"></label></div><details data-import-diff="${row.id}"></details></div>`).join('') || '<p class="helper-text">此備份沒有技能資料。</p>';
  data.rows.forEach(updateImportDiff);updateImportCounts();$('#restoreSettings').checked=false;$('#importMode').value='keep';$('#importSection').scrollIntoView({block:'nearest'});
}
function comparisonKey(left,right){return [left,right].sort().join(':');}
function compareValue(){return {decision:$('#compareDecision').value,reason:$('#compareReason').value};}
function trackComparison(){const left=$('#compareLeft').value,right=$('#compareRight').value;if(!left || !right || left===right)return;const key=comparisonKey(left,right),record=context.state.data.comparisons[key],baseline={decision:record?.decision || 'keep-both',reason:record?.reason || ''},value=compareValue();if(JSON.stringify(value)!==JSON.stringify(baseline)){compareDrafts.set(key,value);context.state.managementDirty.add('comparison:'+key);}else{compareDrafts.delete(key);context.state.managementDirty.delete('comparison:'+key);}}
function comparisonCard(skill){const annotation=saved(skill.id);return `<article class="comparison-card"><h3>${esc(skill.display_name)}</h3><code>${esc(skill.name)}</code><p>${esc(skill.summary)}</p><dl><dt>工作範圍（我的紀錄）</dt><dd>${esc(annotation.scope_note || '尚未記錄')}</dd><dt>是否改檔（我的紀錄）</dt><dd>${({yes:'會修改檔案',no:'維持唯讀',unknown:'未知'})[annotation.modifies_files || 'unknown']}</dd><dt>自動選用宣告</dt><dd>${['codex','claude'].map(host=>`${host==='codex'?'Codex':'Claude'}：${skill.invocation[host].state==='unknown'?'無法判讀':skill.invocation[host].allowed?'允許':'禁止'}（${skill.invocation[host].state==='explicit'?'明確設定':skill.invocation[host].state==='default'?'工具預設':'未知'}）`).join('<br>')}</dd><dt>來源</dt><dd>${esc(skill.source_label)}${skill.plugin?' · '+esc(skill.plugin):''}<br><code>${esc(skill.path)}</code></dd></dl></article>`;}
async function loadComparison(){
  const request=++compareRequest,left=$('#compareLeft').value,right=$('#compareRight').value;
  $('#comparisonForm').querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=true;});
  $('#saveComparison').disabled=true;$('#comparePanels').replaceChildren();$('#compareDiff').textContent='';
  if(!left || !right || left===right){$('#compareState').textContent='請選擇兩個不同技能。';return;}
  $('#compareState').textContent='正在讀取技能原文與比較紀錄…';
  try{
    const result=await context.api(`/api/compare?left=${left}&right=${right}`);
    if(request!==compareRequest || !$('#compareDialog').open)return;
    const key=comparisonKey(left,right),record=result.record;
    if(record)context.state.data.comparisons[key]=record;
    $('#comparePanels').innerHTML=[left,right].map(id=>comparisonCard(skills().find(s=>s.id===id))).join('');
    $('#compareState').textContent=result.identical?'兩份原始內容完全相同；仍可比較來源與個人分工。':'原始內容不同，請依用途與工作範圍判斷分工。';
    $('#compareDiff').textContent=result.diff || '目前顯示範圍沒有文字差異。';$('#diffNote').textContent=result.truncated?'差異預覽已截短；完整原文可在各技能的「原始內容」查看。':'統一差異格式：− 為技能 A，+ 為技能 B。';
    const value=compareDrafts.get(key) || {decision:record?.decision || 'keep-both',reason:record?.reason || ''};
    $('#compareDecision').value=value.decision;$('#compareReason').value=value.reason;
    $('#comparisonSaved').textContent=record?`${record.needs_review?'內容已變動，建議重新檢查。':'已有結論：'+decisions[record.decision]+'。'} ${context.displayedTime(record.checked_at)} · 台灣時間`:'尚未留下整理結論';
    $('#comparisonSaved').classList.toggle('changed-content',Boolean(record?.needs_review));$('#comparisonForm').querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=false;});
  }catch(error){if(request===compareRequest)$('#compareState').textContent=error.message;}
}
function openCompare(left=context.state.selected,right){const items=skills();if(items.length<2){context.toast('至少需要兩個技能才能比較。');return;}left=items.some(s=>s.id===left)?left:items[0].id;right=items.some(s=>s.id===right && s.id!==left)?right:items.find(s=>s.id!==left).id;$('#compareLeft').innerHTML=skillOptions(items,left);$('#compareRight').innerHTML=skillOptions(items,right);$('#compareDialog').showModal();loadComparison();}

export function initializeManagement(ctx){
  context=ctx;context.state.managementDirty=new Set();document.body.insertAdjacentHTML('beforeend',markup);
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.close){$(('#'+button.dataset.close)).close();return;}
    if(button.id==='editMetadataButton' || button.dataset.editMetadata){openMetadata(button.dataset.editMetadata || context.state.selected);return;}
    if(button.dataset.resetDisplay){const form=$('#metadataForm');['alias','summary','category'].forEach(field=>{form.elements.namedItem(field).value='';});form.elements.namedItem('display_mode').value=button.dataset.resetDisplay;trackMeta();return;}
    if(button.id==='dataButton' || button.id==='openDataSettings' || button.id==='recoverDataButton'){try{await openData();}catch(error){report(error);}return;}
    if(button.id==='compareButton' || button.dataset.compareLeft){openCompare(button.dataset.compareLeft,button.dataset.compareRight);return;}
    if(button.id==='chooseBackup'){$('#backupFile').click();return;}
    if(button.id==='downloadBackup'){await busy(button,async()=>{const data=await context.api('/api/backup');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='skillpane-backup-'+new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())+'.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);context.toast('已下載已儲存的整理資料');});}
    if(button.dataset.restore){await busy(button,async()=>showImport(await post('/api/restore/preview',{backup_id:button.dataset.restore})));}
    if(button.id==='applyImport'){await busy(button,async()=>{noDrafts();const result=await post('/api/import/apply',{token:importPreview.token,choices:Object.fromEntries(importPreview.rows.map(row=>[row.id,payloadChoice(row.id)])),mode:$('#importMode').value,restore_settings:$('#restoreSettings').checked});await context.syncState();$('#importSection').hidden=true;$('#dataError').hidden=true;$('#downloadBackup').disabled=false;importPreview=null;await renderData();context.toast(`已匯入 ${result.imported} 筆，套用前的版本已備份`);});}
    if(button.dataset.relinkFrom){await busy(button,async()=>{const to=$(`[data-relink-target="${button.dataset.relinkFrom}"]`).value;if(!to)throw new Error('請先選擇目前的對應技能。');relinkPreview=await post('/api/relink/preview',{from_id:button.dataset.relinkFrom,to_id:to});$('#relinkSection').hidden=false;$('#relinkSection').innerHTML=`<h3>重新關聯預覽</h3><p>${esc(relinkPreview.from_name)} → ${esc(relinkPreview.to_name)}</p><p class="helper-text">${relinkPreview.conflicts.length} 個衝突欄位、${relinkPreview.comparison_conflicts || 0} 筆比較結論衝突。會沿用舊資料的穩定識別與首次發現時間，並先備份。</p><div class="compare-grid"><div><h4>未關聯資料</h4>${annotationView(relinkPreview.incoming)}</div><div><h4>目前技能資料</h4>${annotationView(relinkPreview.current)}</div></div>${relinkPreview.comparisons?.length?`<details><summary>相關比較結論</summary>${relinkPreview.comparisons.map(record=>`<p class="helper-text">${esc(decisions[record.decision])}：${esc(record.reason || "未附理由")} · ${esc(context.displayedTime(record.checked_at))} · 台灣時間</p>`).join("")}</details>`:""}<label class="stack-label">衝突處理<select id="relinkMode"><option value="keep">目前技能的欄位優先</option><option value="replace">舊筆記的欄位優先</option></select></label><button id="applyRelink" class="primary-button">確認重新關聯</button>`;});}
    if(button.id==='applyRelink'){await busy(button,async()=>{noDrafts();await post('/api/relink/apply',{token:relinkPreview.token,mode:$('#relinkMode').value});await context.syncState();$('#relinkSection').hidden=true;await renderData();context.toast('已接回原整理資料');});}
    if(button.id==='saveBackupPolicy'){await busy(button,async()=>{const value=$('#keepBackups').value;await post('/api/backup/settings',{keep_last:value==='all'?null:Number(value)});await context.syncState();await renderData();$('#cleanupSection').hidden=true;context.toast('已儲存保留設定；尚未刪除備份');});}
    if(button.id==='previewCleanup'){await busy(button,async()=>{cleanupPreview=await post('/api/backups/cleanup/preview',{});$('#cleanupSection').hidden=false;$('#cleanupSection').innerHTML=`<h3>舊備份清理預覽</h3><p>${cleanupPreview.files.length} 份，共 ${(cleanupPreview.files.reduce((sum,item)=>sum+item.size,0)/1024).toFixed(1)} KiB；目前資料與最近保留的備份不受影響。</p><ul class="cleanup-files">${cleanupPreview.files.map(file=>`<li><code>${esc(file.id)}</code><br>${esc(context.displayedTime(file.modified_at))} · 台灣時間</li>`).join('')}</ul>${cleanupPreview.files.length?'<label class="check-label"><input id="confirmCleanup" type="checkbox">我已檢查清單，確認永久刪除以上舊備份</label><button id="applyCleanup" class="danger-button" disabled>永久刪除清單中的舊備份</button>':'<p class="helper-text">沒有需要清理的備份。可先調整保留數量。</p>'}`;});}
    if(button.id==='applyCleanup'){await busy(button,async()=>{const result=await post('/api/backups/cleanup/apply',{token:cleanupPreview.token,confirm:$('#confirmCleanup').checked});$('#cleanupSection').hidden=true;await renderData();context.toast(`已清理 ${result.removed} 份舊備份`);});}
  });
  $('#metadataForm').addEventListener('input',trackMeta);$('#metadataForm').addEventListener('change',trackMeta);
  $('#metadataForm').addEventListener('submit',event=>{event.preventDefault();busy($('#saveMetadataButton'),async()=>{const id=editingId,draft=readMeta(),value={...draft,tags:[...new Set(draft.tags.split(/[,，、\n]/).map(v=>v.trim()).filter(Boolean))]};await context.api(`/api/annotation?id=${id}`,{method:'PATCH',body:JSON.stringify(value)});const clean=!metaDrafts.has(id) || JSON.stringify(metaDrafts.get(id))===JSON.stringify(draft);if(clean){metaDrafts.delete(id);context.state.managementDirty.delete('metadata:'+id);}await context.syncState();if(clean && editingId===id && !metaDrafts.has(id))$('#metadataDialog').close();context.toast('整理資訊已儲存');});});
  $('#backupFile').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>4*1024*1024)throw new Error('備份超過 4 MiB。');let data;try{data=JSON.parse(await file.text());}catch{throw new Error('這不是有效的 JSON 備份，未修改現有資料。');}showImport(await post('/api/import/preview',data));}catch(error){report(error);}finally{event.target.value='';}});
  $('#importRows').addEventListener('input',event=>{if(event.target.dataset.targetSearch){const row=importPreview.rows.find(row=>row.id===event.target.dataset.targetSearch);$(`[data-import-choice="${row.id}"]`).innerHTML=targetOptions(row,event.target.value);updateImportDiff(row);updateImportCounts();}});
  $('#importRows').addEventListener('change',event=>{if(event.target.dataset.importChoice){updateImportDiff(importPreview.rows.find(row=>row.id===event.target.dataset.importChoice));updateImportCounts();}});
  $('#cleanupSection').addEventListener('change',event=>{if(event.target.id==='confirmCleanup')$('#applyCleanup').disabled=!event.target.checked;});
  ['#compareLeft','#compareRight'].forEach(selector=>$(selector).addEventListener('change',loadComparison));
  $('#comparisonForm').addEventListener('input',trackComparison);$('#comparisonForm').addEventListener('change',trackComparison);
  $('#compareDialog').addEventListener('close',()=>{if(!$('#compareDialog').open)compareRequest++;});
  $('#comparisonForm').addEventListener('submit',event=>{event.preventDefault();busy($('#saveComparison'),async()=>{const left=$('#compareLeft').value,right=$('#compareRight').value,key=comparisonKey(left,right);await post('/api/comparison',{left_id:left,right_id:right,...compareValue()});compareDrafts.delete(key);context.state.managementDirty.delete('comparison:'+key);await context.syncState();await loadComparison();context.toast('已儲存比較結論');});});
}
