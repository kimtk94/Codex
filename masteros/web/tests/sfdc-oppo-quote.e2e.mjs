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
    const response = await page.goto(base + "/sales/oppo-quote", { waitUntil:"networkidle" });
    // Next.js may paint the form before event handlers are hydrated.
    await page.waitForFunction(() => Object.keys(document.querySelector("#sfdc-mode") || {}).some(k => k.startsWith("__reactProps$")), null, {timeout:10000});
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

    assert.equal(await page.locator("#sfdc-contact-name").inputValue(), "");
    assert.equal(await page.locator("#sfdc-contact-email").getAttribute("readonly"), "");
    await page.locator("#sfdc-contact-name").fill("김민수");
    await page.getByRole("button",{name:"검색어 확인"}).click();
    assert.match(await page.getByRole("status").allTextContents().then(x=>x.join(" ")), /검색어 형식이 확인/);
    assert.equal(await page.getByLabel("고객 검색 결과").count(), 0, "No fabricated Salesforce contacts");
    await page.locator("#sfdc-samples").fill("5");
    await page.locator("#sfdc-depth").fill("1");
    await page.getByRole("button",{name:"검토용 명령서 생성"}).click();
    assert.equal(await page.locator("pre").count(), 0, "No command without verified Contact and Account");
    assert.equal(await page.locator("#sfdc-contact-email").inputValue(), "");
    // Browser-only import of sanitized synthetic desktop evidence:
    // no outbound upload, no CRM mutation, no server-side credential transfer.
    const evidence = {
      version:"sfdc-oppo-contact-readback-v1",
      source:"SFDC_LIGHTNING_READ_ONLY",
      scope:"OPPORTUNITY_LINKED_CONTACTS",
      salesforce_write_performed:false,
      query:"김민수",
      generated_at:new Date().toISOString(),
      unresolved_matches:0,
      candidates:[
        {contact_id:"003000000000AAA",account_id:"001000000000AAA",
         korean_name:"김민수",institution_name:"합성대학교",
         email:"synthetic-a@example.org",linked_opportunity_ids:["006000000000AAA"]},
        {contact_id:"003000000000AAB",account_id:"001000000000AAB",
         korean_name:"김민수",institution_name:"가상대학교",
         email:"synthetic-b@example.org",linked_opportunity_ids:["006000000000AAB"]},
      ],
    };
    await page.locator("#sfdc-local-evidence").setInputFiles({
      name:"sfdc-readonly.json",mimeType:"application/json",
      buffer:Buffer.from(JSON.stringify(evidence),"utf8"),
    });
    await page.getByLabel("고객 검색 결과").waitFor();
    assert.equal(await page.locator("#sfdc-institution-select option").count(), 3);
    await page.locator("#sfdc-institution-select").selectOption("001000000000AAB");
    await page.getByRole("button",{name:/가상대학교/}).click();
    assert.equal(await page.locator("#sfdc-contact-email").inputValue(),"synthetic-b@example.org");
    await page.getByRole("button",{name:"검토용 명령서 생성"}).click();
    assert.match(await page.locator("pre").innerText(), /PENDING_AUTHENTICATED_CONTACT_RECHECK/);
    assert.equal(await page.getByRole("button",{name:"Salesforce 일괄 생성 · 연결 전"}).isDisabled(),true);
    assert.equal(nonReadRequests.length, 0, "Local Contact import and preview must not send POST/PUT/PATCH/DELETE requests");
  } finally {
    if (page) await page.close();
    if (browser) await browser.close();
    if (server) server.kill();
  }
});
