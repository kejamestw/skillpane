// Optional local browser cache; the ordinary CI/browser command is unchanged.
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const cache=path.join(root,'.runtime','playwright-browsers');
const [action,...options]=process.argv.slice(2);
if(!['install','test'].includes(action) || (action==='install' && options.some(value=>value!=='--system-ca'))){
  console.error('Usage: local_browser_tests.cjs install [--system-ca] | test [Playwright test options]');
  process.exit(2);
}
const cli=path.join(root,'node_modules','@playwright','test','cli.js');
if(!fs.existsSync(cli)){
  console.error('Install the locked development dependencies first: npm ci --ignore-scripts');
  process.exit(2);
}
if(action==='test' && !fs.existsSync(cache)){
  console.error('Install the local test browsers first: npm run browsers:local');
  process.exit(2);
}
const env={...process.env,PLAYWRIGHT_BROWSERS_PATH:cache,PLAYWRIGHT_SKIP_BROWSER_GC:'1'};
if(action==='install' && options.includes('--system-ca')){
  if(!process.allowedNodeEnvironmentFlags.has('--use-system-ca')){
    console.error('This Node.js version does not support --use-system-ca. Use a supported Node.js runtime.');
    process.exit(2);
  }
  env.NODE_OPTIONS=[env.NODE_OPTIONS,'--use-system-ca'].filter(Boolean).join(' ');
}
const args=action==='install'?['install','chromium','firefox']:['test',...options];
console.log('Using project-local .runtime/playwright-browsers; no global browser settings are changed.');
const result=spawnSync(process.execPath,[cli,...args],{cwd:root,env,stdio:'inherit',windowsHide:true,shell:false});
if(result.error){console.error('Could not start the local browser tool.');process.exit(1);}
process.exit(Number.isInteger(result.status)?result.status:1);
