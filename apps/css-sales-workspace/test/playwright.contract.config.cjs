'use strict';
// Isolated browser contract tests against local HTML and synthetic owner API.
// This is not a live Vercel SSO session and does not certify Production.
const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
  testDir:'.',
  testMatch:'contract-review.browser.spec.cjs',
  timeout:15000,
  expect:{timeout:6000},
  retries:0,
  workers:1,
  reporter:'line',
  use:{browserName:'chromium',headless:true,trace:'off',screenshot:'off',video:'off'}
});
