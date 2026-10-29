// Personal prompt snippets are text, never HTML or executable instructions.
let context, editing, saving=false;
const drafts=new Map();
const $=selector=>document.querySelector(selector);
const esc=value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const copy=value=>JSON.parse(JSON.stringify(value));
const saved=id=>context.state.data.annotations[id]?.prompts || [];

export function promptsHtml(skill, annotation, icon){
  const prompts=annotation.prompts || [];
  return `<section class="detail-section personal-prompts" aria-label="常用提示詞"><div class="organize-head"><h3 class="section-heading">常用提示詞<span class="muted">我的紀錄${prompts.length?` · ${prompts.length}`:''}</span></h3><button id="addPromptButton" class="quiet-button compact" ${prompts.length>=20?'disabled':''}>＋ 新增提示詞</button></div>${prompts.length?`<div class="saved-prompts">${prompts.map(prompt=>`<article class="saved-prompt"><div class="saved-prompt-head"><h4>${esc(prompt.title)}</h4><div class="inline-actions"><button class="quiet-button compact" data-edit-prompt="${esc(prompt.id)}" aria-label="編輯提示詞 ${esc(prompt.title)}">編輯</button><button class="copy-button" data-copy="${esc(prompt.body)}" aria-label="複製提示詞 ${esc(prompt.title)}">${icon('copy')}</button></div></div><p>${esc(prompt.body)}</p></article>`).join('')}</div>`:'<p class="helper-text prompt-empty">保存你實際常用的說法，下次直接複製使用。</p>'}</section>`;
}

function values(){return {title:$('#promptNameInput').value,body:$('#promptBodyInput').value};}
function track(){
  if(!editing)return;
  const value=values(),changed=JSON.stringify(value)!==JSON.stringify(editing.original);
  if(changed){drafts.set(editing.key,value);context.state.managementDirty.add(editing.key);}
  else{drafts.delete(editing.key);context.state.managementDirty.delete(editing.key);}
  $('#promptDraftState').textContent=changed?'尚未儲存；關閉後保留草稿':'只儲存在這台電腦';
  $('#discardPromptDraft').disabled=!changed;
}
function open(id, seed=false){
  const skillId=context.state.selected, skill=context.state.data.skills.find(item=>item.id===skillId);
  if(!skill || saving)return;
  const prompts=copy(saved(skillId)),prompt=prompts.find(item=>item.id===id);
  if(id && !prompt){context.toast('提示詞已變更，請重新掃描。');return;}
  if(!prompt && prompts.length>=20){context.toast('每個技能最多保存 20 筆提示詞。');return;}
  const key='prompt:'+skillId+':'+(id || 'new');
  editing={skillId,id:prompt?.id || crypto.randomUUID(),key,base:prompts,original:{title:prompt?.title || '',body:prompt?.body || ''},existing:Boolean(prompt)};
  const value=drafts.get(key) || (seed?{title:'常用範例',body:skill.example}:editing.original);
  $('#promptEditorTitle').textContent=prompt?'編輯提示詞':'新增提示詞';
  $('#promptSkillName').textContent='所屬技能：'+skill.name;
  $('#promptNameInput').value=value.title;$('#promptBodyInput').value=value.body;
  $('#removePromptButton').hidden=!prompt;$('#promptRemoveConfirm').hidden=true;
  $('#promptError').hidden=true;$('#promptDialog').showModal();track();$('#promptNameInput').focus();
}
async function persist(removing=false){
  if(!editing || saving)return;
  const edit=editing, value=values();
  if(!removing && !$('#promptForm').reportValidity())return;
  if(!removing && (!value.title.trim() || !value.body.trim())){context.toast('請填寫提示詞名稱與內容。');return;}
  if(context.state.busy.has(edit.skillId)){context.toast('上一筆整理資料仍在儲存，請稍候。');return;}
  const prompt={id:edit.id,...value};
  const next=removing?edit.base.filter(item=>item.id!==edit.id):edit.existing?edit.base.map(item=>item.id===edit.id?prompt:item):[...edit.base,prompt];
  saving=true;context.state.busy.add(edit.skillId);$('#promptError').hidden=true;
  $('#promptForm').querySelectorAll('input,textarea,button').forEach(el=>{el.disabled=true;});
  try{
    const annotation=await context.api('/api/annotation?id='+edit.skillId,{method:'PATCH',body:JSON.stringify({prompts:next,prompts_base:edit.base})});
    context.state.data.annotations[edit.skillId]=annotation;
    drafts.delete(edit.key);context.state.managementDirty.delete(edit.key);
    $('#promptDialog').close();editing=null;
    try{await context.syncState();}catch{context.toast('提示詞已儲存；清單暫時無法更新，請稍後重新掃描。');return;}
    context.toast(removing?'提示詞已移除，先前版本保留在本機備份':'提示詞已儲存，可直接複製使用');
  }catch(error){
    $('#promptError').textContent=error.message;$('#promptError').hidden=false;
    if(error.status===409){try{await context.syncState();}catch{/* Keep the editor and its draft available. */}}
  }finally{
    saving=false;context.state.busy.delete(edit.skillId);
    $('#promptForm').querySelectorAll('input,textarea,button').forEach(el=>{el.disabled=false;});
    track();
  }
}

export function initializePrompts(ctx){
  context=ctx;
  document.body.insertAdjacentHTML('beforeend',`<dialog id="promptDialog" class="management-dialog prompt-dialog" aria-labelledby="promptEditorTitle"><div class="dialog-head"><h2 id="promptEditorTitle">新增提示詞</h2><button id="closePromptButton" class="icon-button" aria-label="關閉提示詞編輯">×</button></div><p id="promptSkillName" class="dialog-description"></p><form id="promptForm" class="management-form"><label>提示詞名稱<input id="promptNameInput" maxlength="80" required placeholder="例如：查詢前先確認環境"></label><label>提示詞內容<textarea id="promptBodyInput" maxlength="4000" rows="7" required placeholder="貼上你常用的完整 prompt，可分行，也可保留 {{環境}} 之類的文字佔位符。"></textarea></label><p class="helper-text">名稱最多 80 字，內容最多 4000 字。只保存文字，使用時複製到對話；佔位符可自行替換。</p><p id="promptError" class="notice" role="alert" hidden></p><div class="dialog-actions"><span id="promptDraftState" class="helper-text" role="status"></span><div class="inline-actions"><button id="discardPromptDraft" type="button" class="quiet-button">放棄草稿</button><button id="savePromptButton" type="submit" class="primary-button">儲存提示詞</button></div></div><button id="removePromptButton" type="button" class="quiet-button remove-prompt" hidden>移除這筆提示詞…</button><div id="promptRemoveConfirm" class="prompt-remove-confirm" hidden><p>確認移除這筆提示詞？儲存前的版本會保留在本機備份。</p><div class="inline-actions"><button id="cancelRemovePrompt" type="button" class="secondary-button">取消</button><button id="confirmRemovePrompt" type="button" class="danger-button">確認移除</button></div></div></form></dialog>`);
  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.id==='addPromptButton')open();
    if(button.id==='saveExamplePrompt')open(undefined,true);
    if(button.dataset.editPrompt)open(button.dataset.editPrompt);
    if(button.id==='closePromptButton' && !saving)$('#promptDialog').close();
    if(button.id==='discardPromptDraft' && !saving){drafts.delete(editing.key);context.state.managementDirty.delete(editing.key);$('#promptNameInput').value=editing.original.title;$('#promptBodyInput').value=editing.original.body;track();}
    if(button.id==='removePromptButton')$('#promptRemoveConfirm').hidden=false;
    if(button.id==='cancelRemovePrompt')$('#promptRemoveConfirm').hidden=true;
    if(button.id==='confirmRemovePrompt')persist(true);
  });
  $('#promptForm').addEventListener('input',track);
  $('#promptForm').addEventListener('submit',event=>{event.preventDefault();persist();});
  $('#promptDialog').addEventListener('cancel',event=>{if(saving)event.preventDefault();});
}
