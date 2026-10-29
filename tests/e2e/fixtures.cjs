// Every test owns a fresh synthetic server on an OS-assigned loopback port.
// No option accepts an existing server URL or the real user's home directory.
const {test:base,expect}=require('@playwright/test');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const path=require('node:path');
const readline=require('node:readline');
const root=path.resolve(__dirname,'../..');

const test=base.extend({
  fixtureURL:async({},use)=>{
    const child=spawn(process.env.SKILLPANE_TEST_PYTHON || 'python',
      ['-B','-u','tests/browser_fixture.py','--port','0'],
      {cwd:root,stdio:['ignore','pipe','pipe'],windowsHide:true});
    // Capture diagnostics in memory only; fixture contents are synthetic.
    let diagnostics='';
    child.stderr.on('data',chunk=>{diagnostics=(diagnostics+chunk).slice(-4000);});
    const lines=readline.createInterface({input:child.stdout});
    try{
      const url=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error('Synthetic server readiness timed out.')),30000);
        const finish=(error,value)=>{clearTimeout(timer);error?reject(error):resolve(value);};
        child.once('error',error=>finish(error));
        child.once('exit',()=>finish(new Error('Synthetic server exited before readiness: '+diagnostics)));
        lines.on('line',line=>{
          const match=/^Independent synthetic fixture: (http:\/\/127\.0\.0\.1:\d+)$/.exec(line);
          if(match)finish(null,match[1]);
        });
      });
      await use(url);
    }finally{
      lines.close();
      if(child.exitCode===null && child.signalCode===null){
        const stopped=once(child,'exit');
        child.kill();
        await stopped;
      }
    }
  },
  page:async({page,fixtureURL},use)=>{
    const errors=[],external=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.context().route('**/*',route=>{
      if(new URL(route.request().url()).origin===fixtureURL)return route.continue();
      external.push('Unexpected external request');return route.abort();
    });
    const response=await page.request.get(fixtureURL+'/api/state');
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).test_fixture).toBe(true);
    await page.goto(fixtureURL);
    await expect(page.locator('.skill-row').first()).toBeVisible();
    await use(page);
    expect(errors,'Uncaught browser errors').toEqual([]);
    expect(external,'Browser must stay inside the synthetic fixture').toEqual([]);
  },
});
module.exports={test,expect};
