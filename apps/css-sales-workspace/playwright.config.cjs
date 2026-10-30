const {defineConfig,devices}=require('@playwright/test');
module.exports=defineConfig({
 testDir:'./e2e',
 timeout:15000,
 expect:{timeout:6000},
 retries:0,
 reporter:'list',
 use:{baseURL:'http://127.0.0.1:4174',
      ...devices['Desktop Chrome'],
      trace:'off',screenshot:'off',video:'off'},
 webServer:{
   command:'node test/browser-fixture-server.js',
   url:'http://127.0.0.1:4174/mail-queue.html',
   reuseExistingServer:false,
   timeout:15000,
 },
});
