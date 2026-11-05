'use strict';
const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
  testDir:'.',
  testMatch:'monthly-revenue.browser.spec.cjs',
  timeout:15000,
  expect:{timeout:6000},
  retries:0,
  workers:1,
  reporter:'line',
  use:{browserName:'chromium',headless:true,trace:'off',screenshot:'off',video:'off'}
});
