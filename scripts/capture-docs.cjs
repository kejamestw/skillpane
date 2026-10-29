// Capture only our freshly spawned synthetic demo, never an existing app URL.
const {chromium,expect}=require('@playwright/test');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {mkdir}=require('node:fs/promises');
const path=require('node:path');
const readline=require('node:readline');
const root=path.resolve(__dirname,'..');
const output=path.join(root,'docs','images');

async function main(){
  const allowed=new Set(['PATH','SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE','LANG','LC_ALL','LD_LIBRARY_PATH']);
  const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>allowed.has(key.toUpperCase())));
  env.PYTHONUTF8='1';env.PYTHONDONTWRITEBYTECODE='1';
  const child=spawn(process.env.SKILLPANE_TEST_PYTHON || 'python',['-B','-u','scripts/demo_fixture.py','--port','0'],
    {cwd:root,env,stdio:['ignore','pipe','pipe'],windowsHide:true});
  const lines=readline.createInterface({input:child.stdout});
  child.stderr.on('data',()=>{}); // Synthetic HTTP logs stay out of published material.
  let browser;
  const errors=[],external=[];
  try{
    const origin=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Synthetic demo readiness timed out')),30000);
      const finish=(error,value)=>{clearTimeout(timer);error?reject(error):resolve(value);};
      child.once('error',error=>finish(error));
      child.once('exit',()=>finish(new Error('Synthetic demo exited before readiness')));
      lines.on('line',line=>{
        const match=/^Synthetic documentation demo: (http:\/\/127\.0\.0\.1:\d+)$/.exec(line);
        if(match)finish(null,match[1]);
      });
    });
    browser=await chromium.launch({headless:true});
    const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1,
      locale:'zh-TW',timezoneId:'Asia/Taipei',colorScheme:'light',reducedMotion:'reduce'});
    await context.route('**/*',route=>{
      if(new URL(route.request().url()).origin===origin)return route.continue();
      external.push('External request');return route.abort();
    });
    const page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    const response=await page.request.get(origin+'/api/state');
    expect(response.ok()).toBeTruthy();
    const snapshot=await response.json();
    expect(snapshot.demo_fixture).toBe(true);
    expect(snapshot.skills).toHaveLength(7);
    expect(snapshot.skills.every(skill=>skill.name.startsWith('demo-'))).toBe(true);
    const originals=async()=>Promise.all(snapshot.skills.map(async skill=>{
      const response=await page.request.get(origin+'/api/skill?id='+encodeURIComponent(skill.id));
      expect(response.ok()).toBeTruthy();return (await response.json()).content;
    }));
    const before=await originals();
    await page.goto(origin);
    await page.locator('.skill-row').filter({hasText:'demo-page-review'}).click();
    await expect(page.locator('#detailPane h2')).toHaveText('檢查頁面細節');
    await expect(page.locator('.saved-prompt h4')).toHaveText('上線前的介面檢查');
    await page.evaluate(()=>document.fonts.ready);
    await mkdir(output,{recursive:true});
    await page.screenshot({path:path.join(output,'desktop.png'),animations:'disabled'});
    await page.locator('#addPromptButton').click();
    await page.locator('#promptNameInput').fill('先確認閱讀順序');
    await page.locator('#promptBodyInput').fill('請用 demo-page-review 檢查這個畫面。\n優先指出標題、主要資訊與操作順序的問題。');
    await page.locator('#promptNameInput').blur();
    await page.screenshot({path:path.join(output,'prompt-editor.png'),animations:'disabled'});
    await page.locator('#closePromptButton').click();

    const mobile=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,
      isMobile:true,hasTouch:true,locale:'zh-TW',timezoneId:'Asia/Taipei',colorScheme:'light',reducedMotion:'reduce'});
    await mobile.route('**/*',route=>{
      if(new URL(route.request().url()).origin===origin)return route.continue();
      external.push('External request');return route.abort();
    });
    const phone=await mobile.newPage();
    phone.on('pageerror',error=>errors.push(error.message));
    await phone.goto(origin);
    await phone.locator('.skill-row').filter({hasText:'demo-page-review'}).click();
    await phone.evaluate(()=>document.fonts.ready);
    await phone.locator('#detailPane').evaluate(node=>node.scrollIntoView({block:'start'}));
    expect(await phone.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await phone.screenshot({path:path.join(output,'mobile.png'),animations:'disabled'});
    const after=await originals();
    expect(after).toEqual(before);
    expect(errors).toEqual([]);expect(external).toEqual([]);
    await mobile.close();
    await context.close();
    console.log('Captured 3 synthetic documentation screenshots; source files unchanged; no external requests.');
  }finally{
    if(browser)await browser.close();
    lines.close();
    if(child.exitCode===null && child.signalCode===null){
      const stopped=once(child,'exit');child.kill();await stopped;
    }
  }
}
main().catch(()=>{console.error('Documentation capture failed; inspect the synthetic demo locally.');process.exitCode=1;});
