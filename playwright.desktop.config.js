import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir:'./e2e/desktop',testMatch:'**/*.spec.js',workers:1,timeout:120000,
  forbidOnly:!!process.env.CI,retries:0,expect:{timeout:15000},
  reporter:[['list'],['html',{open:'never',outputFolder:'playwright-desktop-report'}]],
  outputDir:'test-results-desktop',
  use:{trace:'retain-on-failure',screenshot:'only-on-failure',viewport:{width:1440,height:1000}},
});
