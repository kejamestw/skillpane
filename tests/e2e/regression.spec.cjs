const {readFile}=require('node:fs/promises');
const path=require('node:path');
const {test,expect}=require('./fixtures.cjs');

for(const [file,entry,minChecks] of [
  ['browser-regression.js','runSkillpaneRegression',35],
  ['browser-management.js','runManagementRegression',30],
  ['browser-security.js','runSecurityRegression',15],
  ['browser-prompts.js','runPromptRegression',15],
]){
  test(entry,async({page})=>{
    const source=await readFile(path.resolve(__dirname,'..',file),'utf8');
    // DevTools evaluation does not modify the production CSP or add script routes.
    const result=await page.evaluate(source+'\n'+entry+'()');
    expect(result.passed).toBeGreaterThanOrEqual(minChecks);
    console.log(`${entry}: ${result.passed} synthetic checks passed`);
  });
}

test('IME composition text filters only after composition ends',async({page})=>{
  const rows=page.locator('.skill-row'),count=page.locator('#listCount');
  await expect(rows.first()).toBeVisible();
  const before=await count.textContent();
  await page.locator('#searchInput').evaluate(input=>{
    input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));
    input.value='ㄈ';
    input.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true,data:'ㄈ'}));
  });
  expect(await count.textContent()).toBe(before);
  await page.locator('#searchInput').evaluate(input=>{
    input.value='fixture-149';
    input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'fixture-149'}));
  });
  await expect(rows).toHaveCount(1);
  await expect(page.locator('#detailPane h2')).toHaveText('fixture-149');
});

test('real input, scrolling, and persisted reading preferences',async({page},info)=>{
  await page.locator('#searchInput').fill('fixture-149');
  await expect(page.locator('.skill-row')).toHaveCount(1);
  await expect(page.locator('#detailPane h2')).toHaveText('fixture-149');
  await page.locator('#noteInput').fill('Synthetic keyboard draft');
  await page.locator('#searchInput').fill('fixture-148');
  await page.locator('#searchInput').fill('fixture-149');
  await expect(page.locator('#noteInput')).toHaveValue('Synthetic keyboard draft');
  await page.locator('#saveNoteButton').click();
  await expect(page.locator('#noteState')).toHaveText('筆記已儲存');
  await page.locator('#sidebarToggle').click();
  await expect(page.locator('#sidebarToggle')).toHaveAttribute('aria-expanded','false');
  await page.locator('#quickSettingsButton').click();
  await page.locator('#textSizeSelect').selectOption('large');
  await page.locator('#closeSettings').click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-text-size','large');
  await expect(page.locator('#sidebarToggle')).toHaveAttribute('aria-expanded','false');
  await page.locator('#searchInput').fill('');
  const list=page.locator('#skillList');
  await list.hover();await page.mouse.wheel(0,1800);
  await expect.poll(()=>list.evaluate(node=>node.scrollTop)).toBeGreaterThan(0);
  await page.locator('#searchInput').fill('fixture-149');
  await page.locator('#tab-raw').click();
  await expect(page.locator('.raw-content')).toBeVisible();
  if(info.project.name.includes('mobile')){
    await page.locator('#tabContent').hover();await page.mouse.wheel(0,1800);
    await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBeGreaterThan(0);
  }else{
    const detail=page.locator('#tabContent');await detail.hover();await page.mouse.wheel(0,1800);
    await expect.poll(()=>detail.evaluate(node=>node.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(()=>window.scrollY)).toBe(0);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
