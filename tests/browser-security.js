// Independent synthetic fixture only. Never run writes against a real library.
async function runSecurityRegression(){
  const api=async(path='/api/state',options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-Skillpane-Client':'1'}});const body=await response.json();if(!response.ok)throw new Error(body.error);return body;};
  const initial=await api();if(initial.test_fixture!==true)throw new Error('Only the independent fixture server is permitted.');
  const skill=initial.skills.find(item=>item.name==='fixture-148');
  const original=initial.annotations[skill.id] || {};
  const defaults={alias:'',summary:'',category:'',tags:[],origin_reason:'',scope_note:'',note:''};
  const payload='<img src=x onerror="window.__skillpaneXss=1">';
  const fingerprints=value=>JSON.stringify(value.skills.map(item=>[item.name,item.sha256]));
  const checks=[];
  const assert=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  const until=async test=>{const end=performance.now()+30000;while(!test()){if(performance.now()>end)throw new Error('UI timeout');await new Promise(resolve=>setTimeout(resolve,40));}};
  const refresh=async()=>{document.querySelector('#refreshButton').click();await until(()=>!document.querySelector('#refreshButton').disabled);};
  const patch=value=>api('/api/annotation?id='+skill.id,{method:'PATCH',body:JSON.stringify(value)});
  try{
    await patch({alias:payload,summary:payload,category:'安全測試',tags:['tag<img src=x>'],origin_reason:payload,scope_note:payload,note:payload});
    await refresh();
    document.querySelector('.nav-item[data-view="personal"]').click();
    const input=document.querySelector('#searchInput');input.value=skill.name;input.dispatchEvent(new Event('input',{bubbles:true}));
    await until(()=>document.querySelector('#detailPane h2')?.textContent===payload);
    assert(document.querySelector('#skillList').textContent.includes(payload),'清單將惡意標籤視為文字');
    assert(!document.querySelector('#skillList img,#skillList svg[onload],#detailPane img,#detailPane [onerror]'),'列表與詳情未建立注入的可執行元素');
    assert(document.querySelector('#noteInput').value===payload,'筆記中的標籤維持文字');
    document.querySelector('#editMetadataButton').click();
    assert(document.querySelector('[name="alias"]').value===payload && !document.querySelector('#metadataDialog img'),'編輯欄位保留文字並安全顯示');
    document.querySelector('[data-close="metadataDialog"]').click();
    assert(window.__skillpaneXss!==1,'惡意事件處理常式未執行');
  }finally{
    await patch({...defaults,...original});await refresh();
  }
  assert(fingerprints(await api())===fingerprints(initial),'安全顯示測試未修改技能原文');
  return {passed:checks.length,checks};
}
