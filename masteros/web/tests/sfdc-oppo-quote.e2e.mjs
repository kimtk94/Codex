/** Synthetic-only browser smoke test. Never logs in to Salesforce or uses client data. */
import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { chromium } from "playwright";

const port = 31389;
const base = "http://127.0.0.1:" + port;
let server;
let browser;

async function waitForServer() {
  for (let attempt = 0; attempt < 90; attempt++) {
    if (server.exitCode !== null) throw Error("Next.js process exited prematurely");
    try {
      const res = await fetch(base + "/sales/oppo-quote", { signal: AbortSignal.timeout(1000) });
      if (res.status === 200) return;
    } catch { /* poll until ready */ }
    await delay(500);
  }
  throw Error("Next.js command workspace did not become ready");
}

test("protected-deploy equivalent local browser: PMP request never performs CRM Save", {timeout: 110000}, async () => {
  server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--port", String(port)], {
    cwd: process.cwd(),
    env: {...process.env, NEXT_TELEMETRY_DISABLED:"1"},
    stdio: "ignore",
  });
  let page;
  try {
    await waitForServer();
    browser = await chromium.launch({ headless:true });
    page = await browser.newPage();
    const nonReadRequests = [];
    page.on("request", request => {
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
        nonReadRequests.push({ method: request.method(), url: new URL(request.url()).pathname });
      }
    });
    const response = await page.goto(base + "/sales/oppo-quote", { waitUntil:"domcontentloaded" });
    assert.equal(response.status(), 200);
    assert.equal(await page.getByRole("heading", {name:"Opportunity + Quotation"}).count(), 1);
    assert.equal(await page.locator("#sfdc-contact-email").inputValue(), "");
    assert.equal(await page.locator("#sfdc-mode").inputValue(), "PE250");
    assert.equal((await page.locator("#sfdc-depth + span").textContent()).trim(), "M reads");
    assert.equal(await page.getByRole("button", {name:"Salesforce 일괄 생성 · 연결 전"}).isDisabled(), true);

    await page.locator("#sfdc-mode").selectOption("PE150");
    assert.equal((await page.locator("#sfdc-depth + span").textContent()).trim(), "Gb");
    await page.locator("#sfdc-mode").selectOption("PE250");
    assert.equal((await page.locator("#sfdc-depth + span").textContent()).trim(), "M reads");

    await page.locator("#sfdc-contact-email").fill("researcher@example.org");
    await page.locator("#sfdc-samples").fill("5");
    await page.locator("#sfdc-depth").fill("1");
    await page.getByRole("button",{name:"검토용 명령서 생성"}).click();
    const preview = JSON.parse(await page.locator("pre").textContent());
    assert.equal(preview.request.contact_email, "researcher@example.org");
    assert.equal(preview.request.sample_count, 5);
    assert.equal(preview.request.depth_per_sample, 1);
    assert.equal(preview.request.depth_unit, "M reads");
    assert.equal(preview.summary.nominal_total_depth, 5);
    assert.equal(preview.salesforce_save_allowed, false);
    assert.equal(preview.opportunity_created, false);
    assert.equal(preview.quotation_created, false);
    assert.equal(nonReadRequests.length, 0, "Browser draft should not send any POST/PUT/PATCH/DELETE requests");
  } finally {
    if (page) await page.close();
    if (browser) await browser.close();
    if (server) server.kill();
  }
});
