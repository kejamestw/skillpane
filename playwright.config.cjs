const {defineConfig}=require('@playwright/test');

module.exports=defineConfig({
  testDir:'./tests/e2e',
  outputDir:'.runtime/playwright-results',
  timeout:120000,
  expect:{timeout:10000},
  workers:2,
  retries:0,
  forbidOnly:!!process.env.CI,
  reporter:'line',
  use:{headless:true,trace:'off',screenshot:'off',video:'off'},
  projects:[
    {name:'chromium-desktop',use:{browserName:'chromium',viewport:{width:1280,height:720}}},
    {name:'chromium-compact',use:{browserName:'chromium',viewport:{width:1024,height:480}}},
    {name:'chromium-mobile',use:{browserName:'chromium',viewport:{width:390,height:844},isMobile:true,hasTouch:true}},
    {name:'firefox-desktop',use:{browserName:'firefox',viewport:{width:1280,height:720}}},
  ],
});
