import {defineConfig,devices} from '@playwright/test';

export default defineConfig({
  testDir:'./e2e',testMatch:'**/*.spec.js',testIgnore:'**/desktop/**',fullyParallel:true,
  forbidOnly:!!process.env.CI,retries:process.env.CI?1:0,workers:2,
  timeout:60000,expect:{timeout:10000},
  reporter:[['list'],['html',{open:'never'}]],outputDir:'test-results',
  use:{viewport:{width:1440,height:1000},trace:'retain-on-failure',screenshot:'only-on-failure',video:'retain-on-failure',actionTimeout:10000,navigationTimeout:20000},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome'],viewport:{width:1440,height:1000}}}],
});
