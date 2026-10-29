// Paste this function into the fixture page console, then run:
// await runSkillpaneRegression()
// Refuses to change any UI unless the independent fixture server is verified.
async function runSkillpaneRegression() {
  const snapshot=await fetch('/api/state').then(r=>r.json());
  if(snapshot.test_fixture!==true)throw new Error('Only the independent synthetic fixture server is permitted.');
  const $=selector=>document.querySelector(selector);
  const rows=()=>[...document.querySelectorAll('.skill-row')];
  const checks=[];
  function check(condition,name){if(!condition)throw new Error(name);checks.push(name);}
  async function until(predicate,name){
    const end=performance.now()+20000;
    while(performance.now()<end){if(await predicate())return;await new Promise(r=>setTimeout(r,30));}
    throw new Error('Timeout: '+name);
  }
  function input(selector,value){const node=$(selector);node.value=value;node.dispatchEvent(new Event('input',{bubbles:true}));}
  function view(name){$(`.nav-item[data-view="${name}"]`).click();}
  const search=value=>input('#searchInput',value);
  function unloadBlocked(){const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}
  const fixture=snapshot.skills.find(s=>s.name==='fixture-000' && s.source==='personal');
  const other=snapshot.skills.find(s=>s.name==='fixture-149');
  const originalTheme=localStorage.getItem('skillpane-theme');
  const digest=JSON.stringify(snapshot.skills.map(s=>[s.id,s.sha256]));
  check(snapshot.skills.length===154 && !snapshot.skills.some(s=>s.description.startsWith('Nested ')),'技能內附副本不膨脹清單與搜尋數量');
  await until(()=>rows().length>0,'initial list');
  view('personal');search('fixture-000');
  check(rows().length===1 && rows()[0].dataset.skill===fixture.id,'搜尋僅顯示符合項目');
  check($('#detailPane h2').textContent==='fixture-000','右側詳情跟隨搜尋結果');
  search('__no_skill_matches__');
  check(rows().length===0 && !$('#favoriteButton') && !$('#noteInput'),'沒有結果時清除右側整理控制項');
  search('fixture-149');
  check(rows().length===1 && rows()[0].dataset.skill===other.id && $('#detailPane h2').textContent==='fixture-149','空結果恢復後選取正確');

  input('#noteInput','synthetic unsaved draft');
  check(unloadBlocked(),'未儲存草稿會觸發離頁保護');
  search('fixture-000');search('fixture-149');
  check($('#noteInput').value==='synthetic unsaved draft','搜尋切換保留筆記草稿');
  view('other');view('personal');search('fixture-149');
  check($('#noteInput').value==='synthetic unsaved draft','切換來源保留筆記草稿');
  $('#sortButton').click();
  check($('#noteInput').value==='synthetic unsaved draft','排序保留目前選取與草稿');
  $('#refreshButton').click();await until(()=>!$('#refreshButton').disabled,'refresh draft');
  check($('#noteInput').value==='synthetic unsaved draft','重新掃描保留尚未儲存的草稿');
  input('#noteInput','');
  check(!unloadBlocked() && !$('#noteState').textContent.includes('尚未儲存'),'還原原值解除草稿與離頁保護');
  $('#sortButton').click();

  view('personal');
  $('[data-filter="設計與動畫"]').click();
  check(rows().length===2 && rows().some(row=>row.getAttribute('aria-pressed')==='true'),'分類篩選後保有可見的選取項目');
  $('[data-filter="開發工具"]').click();
  check(rows().every(row=>row.textContent.includes('開發工具')) && $('#detailPane h2').textContent.includes('fixture'),'切換分類後右側顯示該分類技能');

  view('personal');search('fixture-000');
  $('#favoriteButton').click();
  await until(()=>$('[data-count="favorites"]').textContent==='1','favorite save');
  view('favorites');
  check(rows().length===1 && rows()[0].dataset.skill===fixture.id,'收藏儲存後立即出現在收藏清單');
  await until(()=>$('#favoriteButton')?.getAttribute('aria-pressed')==='true','favorite detail');
  $('#favoriteButton').click();
  await until(()=>rows().length===0 && !$('#favoriteButton'),'unfavorite exit');
  check($('[data-count="favorites"]').textContent==='0','取消收藏後清單與詳情同步清空');

  view('review');
  check(rows().length===0,'工具政策差異不當作待整理錯誤');
  view('personal');search('manual-only');
  check(Boolean($('#detailPane .advisory')) && !$('#detailPane .notice'),'設定差異以一般提示呈現');
  $('#tab-source').click();
  check($('#tabContent').textContent.includes('採工具預設') && $('#tabContent').textContent.includes('明確設定'),'來源頁區分明確設定與工具預設');
  check($('#tabContent').textContent.includes('SKILL.md:4'),'設定證據對應原始檔行號');

  view('personal');search('fixture-000');
  $('#statusSelect').value='review';$('#statusSelect').dispatchEvent(new Event('change',{bubbles:true}));
  await until(()=>$('[data-count="review"]').textContent==='1','status review');
  view('review');
  check(rows().length===1 && rows()[0].dataset.skill===fixture.id,'整理標記立即更新待整理清單');
  $('#statusSelect').value='keep';$('#statusSelect').dispatchEvent(new Event('change',{bubbles:true}));
  await until(()=>rows().length===0 && !$('#statusSelect'),'status keep exit');
  check($('[data-count="review"]').textContent==='0','保留使用後自待整理移除並清空詳情');

  view('personal');search('fixture-000');
  input('#noteInput','synthetic-search-note');$('#saveNoteButton').click();
  await until(()=>$('#noteState')?.textContent==='筆記已儲存','note save');
  search('synthetic-search-note');
  check(rows().length===1 && rows()[0].dataset.skill===fixture.id,'儲存後可依本機筆記搜尋');
  input('#noteInput','');$('#saveNoteButton').click();
  await until(()=>rows().length===0 && !$('#noteInput'),'saved note no longer matches');
  check(!unloadBlocked(),'筆記儲存並離開篩選結果後沒有殘留草稿');

  view('personal');search('emil-design-eng');
  check($('#detailPane').textContent.includes('Skillpane 中文別名'),'中文別名標示由面板補充');
  $('#tab-source').click();
  check($('#tabContent').textContent.includes("Emil Kowalski's philosophy") && $('#tabContent').textContent.includes('非原作者指令'),'原始描述與範例來源可查閱');
  $('#tab-raw').click();await until(()=>$('.raw-content'),'raw content');
  check($('.raw-content').textContent.includes('<script>not executable</script>') && !$('.raw-content script'),'原始技能內容以純文字呈現');

  view('overlaps');
  check($('#listCount').textContent.startsWith('1 組') && !$('#skillList').textContent.includes('同分類工具'),'同名檢查不混入分類相關工具');
  view('related');
  check($('#listCount').textContent.startsWith('2 組') && $('#listFootnote').textContent.includes('不是重複'),'相關工具獨立呈現並說明判定限制');
  view('other');
  check(rows().length===1,'外掛快取多版本收合');
  check(!$('#tabContent [data-copy^="$fixture-000"]'),'外掛命名空間未知時不猜呼叫指令');

  view('personal');
  const list=$('#skillList');list.scrollTop=list.scrollHeight;
  await new Promise(r=>requestAnimationFrame(r));
  check(list.scrollHeight>list.clientHeight && list.scrollTop>0,'長技能清單可捲動到底部');
  const last=rows().at(-1),beforeScroll=list.scrollTop;
  last.click();
  check(rows().at(-1)===last && Math.abs(list.scrollTop-beforeScroll)<2,'選取技能不重建清單或跳回頂端');
  check($('#tabContent').clientHeight>40,'右側詳情具有可讀取的內容區');
  if(!matchMedia('(max-width: 620px)').matches){
    $('#tab-raw').click();await until(()=>$('.raw-content'),'long raw detail');
    const detail=$('#tabContent');detail.scrollTop=detail.scrollHeight;
    check(detail.scrollHeight>detail.clientHeight && detail.scrollTop>0,'桌面右側詳情可獨立捲動');
    check(document.documentElement.scrollHeight<=innerHeight+1,'桌面避免整頁與面板雙層捲動');
  }else{
    check(document.documentElement.scrollHeight>innerHeight,'手機維持整頁自然捲動');
  }
  check(document.documentElement.scrollWidth<=innerWidth+1,'頁面沒有水平溢出');
  $('#scopeButton').click();
  check($('#scopeDialog').open && $('#scopeRoots').children.length===4,'掃描範圍可從面板查看');
  check($('#scopeDialog').textContent.includes('未掃描各專案'),'掃描範圍說明不宣稱涵蓋專案');
  check($('#scopeDialog').textContent.includes('不再往下掃描'),'掃描範圍說明技能資料夾邊界');
  $('#closeScope').click();
  const theme=$('#themeSelect');theme.value='dark';theme.dispatchEvent(new Event('change',{bubbles:true}));
  check(document.documentElement.dataset.theme==='dark','深色主題可切換');
  theme.value='light';theme.dispatchEvent(new Event('change',{bubbles:true}));
  check(document.documentElement.dataset.theme==='light','淺色主題可切換');
  theme.value=originalTheme || 'system';theme.dispatchEvent(new Event('change',{bubbles:true}));
  $('#refreshButton').click();await until(()=>!$('#refreshButton').disabled,'rescan');
  const after=await fetch('/api/state').then(r=>r.json());
  check(digest===JSON.stringify(after.skills.map(s=>[s.id,s.sha256])),'全部 UI 操作與重新掃描均未改寫技能本體');
  check(Object.entries(after.annotations).every(([id,a])=>id===fixture.id?!a.favorite && (a.status || 'keep')==='keep' && !a.note:JSON.stringify(a)===JSON.stringify(snapshot.annotations[id] || {})),'測試完成後還原假資料的收藏筆記與標記');
  view('personal');
  return {passed:checks.length,viewport:{width:innerWidth,height:innerHeight},checks};
}
