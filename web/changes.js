// Scan observations are text only. This module never executes skill contents.
const $=selector=>document.querySelector(selector);
const esc=value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const kinds={added:'新增',changed:'內容與版本變更',missing:'未再掃到'};
const sources={personal:'個人技能',managed:'Claude 同步',system:'系統內建',plugin:'外掛快取'};
let context;

function summary(event){
  if(event.kind==='added')return '這次掃描新出現，也可能是再次加入或重新可讀。';
  if(event.kind==='missing')return '當時未再掃到；可能與路徑、權限或檔案移動有關。';
  const before=event.before,after=event.after,parts=[];
  if(before.sha256!==after.sha256)parts.push('SKILL.md 內容變更');
  if(before.name!==after.name)parts.push(`名稱：${before.name} → ${after.name}`);
  if(before.version!==after.version)parts.push(`選用快取：${before.version || '未標示'} → ${after.version || '未標示'}`);
  if(before.cache!==after.cache)parts.push('快取集合變更');
  if(before.source!==after.source || before.plugin!==after.plugin)parts.push('來源資訊變更');
  return parts.join(' · ');
}

export function renderChanges(){
  if(!context?.state.data)return;
  const data=context.state.data.changes;
  $('#changesCount').textContent=data?.events.length || 0;
  if(!$('#changesDialog').open)return;
  const events=data?.events || [],kind=$('#changeKind').value,query=$('#changeSearch').value.trim().toLowerCase();
  $('#changesBaseline').textContent=data?.baseline_at?`基準建立於 ${context.displayedTime(data.baseline_at)} · 台灣時間`:'尚未建立掃描基準';
  $('#changesRetention').textContent=`最多保留最近 ${data?.limit || 300} 筆；較舊紀錄自動移出。`;
  $('#changesError').hidden=!data?.error;$('#changesError').textContent=data?.error || '';
  $('#changesSkipped').hidden=!data?.skipped;
  $('#changesSkipped').textContent=`這次掃描有 ${data?.skipped || 0} 項略過，暫不產生「未再掃到」事件；其他可讀取項目的變更照常記錄。`;
  const filtered=events.filter(event=>{
    const item=event.after || event.before;
    return (!kind || event.kind===kind) && [item.name,item.plugin,sources[item.source],summary(event)].join(' ').toLowerCase().includes(query);
  });
  $('#changesResult').textContent=`${filtered.length} / ${events.length} 筆紀錄`;
  $('#changeStats').textContent=Object.entries(kinds).map(([key,label])=>`${label} ${events.filter(e=>e.kind===key).length}`).join(' · ');
  const live=new Set(context.state.data.skills.map(skill=>skill.id));
  $('#changesList').innerHTML=filtered.length?filtered.map(event=>{
    const item=event.after || event.before;
    return `<article class="change-row" data-change-kind="${event.kind}"><div class="change-row-main"><span class="change-kind change-${event.kind}">${kinds[event.kind]}</span><strong>${esc(item.name)}</strong><p>${esc(summary(event))}</p><small>${sources[item.source]}${item.plugin?' · '+esc(item.plugin):''} · ${esc(context.displayedTime(event.observed_at))} 台灣時間</small></div>${live.has(event.skill_id)?`<button class="secondary-button" data-change-skill="${esc(event.skill_id)}">查看目前技能</button>`:''}</article>`;
  }).join(''):`<div class="change-empty"><strong>${events.length?'沒有符合的紀錄':data?.baseline_at?'基準已建立，尚無變更紀錄':'尚無變更紀錄'}</strong><p>${events.length?'試著調整搜尋或類型。':'首次掃描不會把既有技能列為新增；之後重新掃描或啟動程式時會比較變化。'}</p></div>`;
}

export function initializeChanges(ctx){
  context=ctx;
  document.body.insertAdjacentHTML('beforeend',`<dialog id="changesDialog" class="management-dialog changes-dialog" aria-labelledby="changesTitle"><div class="dialog-head"><div><h2 id="changesTitle">技能變更紀錄</h2><p id="changesBaseline" class="helper-text"></p></div><button id="closeChanges" class="icon-button" aria-label="關閉變更紀錄">×</button></div><p class="dialog-description">記錄掃描觀察到的變化；不是安裝、使用或停用紀錄。</p><p id="changesError" class="notice" role="alert" hidden></p><p id="changesSkipped" class="notice" hidden></p><div class="changes-toolbar"><label class="search-field"><input id="changeSearch" type="search" placeholder="搜尋技能或來源" aria-label="搜尋變更紀錄"></label><select id="changeKind" aria-label="變更類型"><option value="">全部類型</option><option value="added">新增</option><option value="changed">內容與版本變更</option><option value="missing">未再掃到</option></select><button id="scanChanges" class="secondary-button">重新掃描</button></div><p id="changeStats" class="helper-text"></p><div id="changesList" class="changes-list" tabindex="0" role="region" aria-label="技能變更紀錄清單"></div><div class="changes-footer"><span id="changesResult"></span><span id="changesRetention"></span></div><details class="changes-privacy"><summary>紀錄範圍與隱私</summary><p>只比較 SKILL.md 與已掃描的外掛快取；輔助腳本與其他檔案不在比對範圍。只保存名稱、來源、版本與指紋，不保存技能全文、絕對路徑或筆記。紀錄只留在本機，不包含於目前的清單匯出或整理資料備份。</p></details></dialog>`);
  $('#changesButton').addEventListener('click',()=>{if(!context.state.data)return;$('#changesDialog').showModal();renderChanges();});
  $('#closeChanges').addEventListener('click',()=>$('#changesDialog').close());
  $('#changeKind').addEventListener('change',renderChanges);
  $('#changeSearch').addEventListener('input',renderChanges);
  $('#scanChanges').addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{await context.refresh();}finally{button.disabled=false;renderChanges();}});
  $('#changesList').addEventListener('click',event=>{const button=event.target.closest('[data-change-skill]');if(!button)return;$('#changesDialog').close();context.openSkill(button.dataset.changeSkill);});
}
