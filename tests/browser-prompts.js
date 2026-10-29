// Synthetic fixture only. Clipboard writes are intercepted and never touch the OS.
async function runPromptRegression(){
  const $=selector=>document.querySelector(selector),checks=[];
  const assert=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  const until=async(test,label)=>{const end=performance.now()+15000;while(!test()){if(performance.now()>end)throw new Error('Timeout: '+label);await new Promise(resolve=>setTimeout(resolve,35));}};
  const api=async(path='/api/state',options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-Skillpane-Client':'1'}});const value=await response.json();if(!response.ok)throw new Error(value.error);return value;};
  const initial=await api();if(initial.test_fixture!==true)throw new Error('Independent synthetic fixture required.');
  const skill=initial.skills.find(item=>item.name==='fixture-148'),original=initial.annotations[skill.id] || {};
  const input=(selector,value)=>{const el=$(selector);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));};
  const search=value=>input('#searchInput',value);
  const submit=async()=>{$('#promptForm').requestSubmit();await until(()=>!$('#promptDialog').open,'prompt save');await until(()=>!$('#savePromptButton').disabled,'save settled');};
  const clipboard=navigator.clipboard.writeText;let copied;
  navigator.clipboard.writeText=async value=>{copied=value;};
  const preferences={size:localStorage.getItem('skillpane-text-size'),sidebar:localStorage.getItem('skillpane-sidebar-hidden')};
  try{
    await api('/api/annotation?id='+skill.id,{method:'PATCH',body:JSON.stringify({prompts:[],prompts_base:original.prompts || []})});
    $('#refreshButton').click();await until(()=>!$('#refreshButton').disabled,'prepare fixture');
    $('.nav-item[data-view="personal"]').click();search(skill.name);await until(()=>$('#addPromptButton'),'selected fixture');
    assert(parseFloat(getComputedStyle(document.documentElement).fontSize)>=16,'預設文字基準至少 16px');
    assert(parseFloat(getComputedStyle($('#noteInput')).fontSize)>=16,'筆記與主要內容至少 16px');
    const before=$('.main').getBoundingClientRect().width;$('#sidebarToggle').click();
    assert(getComputedStyle($('.sidebar')).display==='none' && $('.main').getBoundingClientRect().width>before && $('#sidebarToggle').getAttribute('aria-expanded')==='false','側邊欄可隱藏並讓出內容空間');
    assert(localStorage.getItem('skillpane-sidebar-hidden')==='1','側邊欄選擇已保存');
    $('#quickSettingsButton').click();const size=$('#textSizeSelect');size.value='large';size.dispatchEvent(new Event('change',{bubbles:true}));
    assert(parseFloat(getComputedStyle(document.documentElement).fontSize)>=18 && localStorage.getItem('skillpane-text-size')==='large','字級設定放大且可保存');$('#closeSettings').click();
    $('#sidebarToggle').click();assert($('#sidebarToggle').getAttribute('aria-expanded')==='true','側邊欄可以重新展開');
    input('#noteInput','Synthetic unsaved note draft');
    $('#addPromptButton').click();input('#promptNameInput','環境確認');input('#promptBodyInput','SyntheticPromptKeyword\n先確認 {{環境}} 再查詢。');await submit();
    await until(()=>$('.saved-prompt'),'new card');
    assert($('.saved-prompt').textContent.includes('環境確認'),'新增提示詞顯示獨立卡片');
    assert($('#noteInput').value==='Synthetic unsaved note draft','儲存提示詞保留未儲存的筆記草稿');
    $('.saved-prompt [data-copy]').click();await until(()=>copied!==undefined,'clipboard spy');
    assert(copied==='SyntheticPromptKeyword\n先確認 {{環境}} 再查詢。','複製保留完整多行提示詞');
    $('.saved-prompt [data-edit-prompt]').click();input('#promptNameInput','Unfinished prompt draft');$('#closePromptButton').click();$('.saved-prompt [data-edit-prompt]').click();
    assert($('#promptNameInput').value==='Unfinished prompt draft','關閉編輯後提示詞草稿仍在');
    $('#discardPromptDraft').click();assert($('#promptNameInput').value==='環境確認','可以明確放棄提示詞草稿');$('#closePromptButton').click();
    const hostile='<img src=x onerror="window.__promptXss=1">';$('#addPromptButton').click();input('#promptNameInput',hostile);input('#promptBodyInput','</textarea><svg onload="window.__promptXss=1"></svg>');await submit();await until(()=>document.querySelectorAll('.saved-prompt').length===2,'two cards');
    assert($('.personal-prompts').textContent.includes(hostile) && !$('.personal-prompts img,.personal-prompts svg[onload]') && window.__promptXss!==1,'多筆提示詞中的 HTML 維持文字顯示');
    search('SyntheticPromptKeyword');assert($('.skill-row')?.dataset.skill===skill.id,'可用已儲存提示詞內容搜尋技能');search(skill.name);
    const backup=await api('/api/backup');assert(backup.records.find(item=>item.id===skill.id).annotation.prompts.length===2,'整理資料備份包含多筆提示詞');
    $('#dataButton').click();await until(()=>$('#dataDialog').open,'data dialog');
    const transfer=new DataTransfer();transfer.items.add(new File([JSON.stringify(backup)],'synthetic-prompts.json',{type:'application/json'}));$('#backupFile').files=transfer.files;$('#backupFile').dispatchEvent(new Event('change',{bubbles:true}));await until(()=>!$('#importSection').hidden,'import preview');
    assert($('#importRows').textContent.includes('常用提示詞') && !$('#importRows').textContent.includes('[object Object]') && !$('#importRows img'),'匯入預覽顯示可閱讀且安全的提示詞內容');$('[data-close="dataDialog"]').click();
    const second=document.querySelectorAll('.saved-prompt [data-edit-prompt]')[1];second.click();$('#removePromptButton').click();$('#cancelRemovePrompt').click();
    assert($('#promptRemoveConfirm').hidden && document.querySelectorAll('.saved-prompt').length===2,'取消移除不會刪除提示詞');$('#removePromptButton').click();$('#confirmRemovePrompt').click();await until(()=>!$('#promptDialog').open && document.querySelectorAll('.saved-prompt').length===1,'remove second');
    assert($('.saved-prompt h4').textContent==='環境確認','移除指定提示詞保留其他項目');
    $('.saved-prompt [data-edit-prompt]').click();input('#promptNameInput','Draft across conflict');const current=await api(),base=current.annotations[skill.id].prompts;
    await api('/api/annotation?id='+skill.id,{method:'PATCH',body:JSON.stringify({prompts:base.map(p=>({...p,body:'Other synthetic window'})),prompts_base:base})});
    $('#promptForm').requestSubmit();await until(()=>!$('#promptError').hidden && !$('#savePromptButton').disabled,'conflict');
    assert($('#promptDialog').open && $('#promptNameInput').value==='Draft across conflict' && $('#promptError').textContent.includes('其他視窗'),'衝突拒絕覆寫並保留使用者草稿');
    $('#discardPromptDraft').click();$('#closePromptButton').click();
    $('#saveExamplePrompt').click();assert($('#promptBodyInput').value===skill.example,'可以用面板示範建立自己的提示詞');$('#discardPromptDraft').click();$('#closePromptButton').click();
    assert($('#noteInput').value==='Synthetic unsaved note draft','完整提示詞操作期間筆記草稿保持不變');
  }finally{
    if($('#promptDialog').open){$('#discardPromptDraft').click();$('#closePromptButton').click();}
    if($('#dataDialog').open)$('[data-close="dataDialog"]').click();
    const current=await api();await api('/api/annotation?id='+skill.id,{method:'PATCH',body:JSON.stringify({prompts:original.prompts || [],prompts_base:current.annotations[skill.id]?.prompts || []})});
    if($('#noteInput'))input('#noteInput',original.note || '');
    $('#quickSettingsButton').click();$('#textSizeSelect').value=preferences.size || 'standard';$('#textSizeSelect').dispatchEvent(new Event('change',{bubbles:true}));$('#closeSettings').click();
    if($('.app-shell').classList.contains('sidebar-hidden')!==(preferences.sidebar==='1'))$('#sidebarToggle').click();
    $('#refreshButton').click();await until(()=>!$('#refreshButton').disabled,'restore refresh');
    navigator.clipboard.writeText=clipboard;
  }
  return {passed:checks.length,checks};
}
