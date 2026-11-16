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
    // General service intake stays browser-local and cannot perform CRM writes.
    const general = await page.goto(base + "/sales/oppo-quote/new", {waitUntil:"networkidle"});
    assert.equal(general.status(), 200);
    assert.equal(await page.getByRole("heading",{name:"신규 Oppo + Quote"}).count(),1);
    await page.locator("#new-account").fill("합성대학교");
    await page.locator("#new-contact").fill("김민수");
    await page.locator("#new-service").selectOption("RNA");
    await page.locator("#new-samples").fill("48");
    await page.locator("#new-production").fill("6");
    await page.locator("#new-cloud").selectOption("YES");
    await page.getByRole("button",{name:"검토용 요청서 확인"}).click();
    assert.match(await page.locator("pre").innerText(), /HOLD_SFDC_ID_PRODUCT_PRICE_APPROVAL/);
    assert.match(await page.locator("pre").innerText(), /"alicloudQuantity": 3/);
    // Local 2026-KRW-only price evidence fixture (synthetic), 0 server writes.
    assert.match(await page.getByLabel("2026 KRW 가격 비교").innerText(),/KRW 공정별 가격 비교/);
    const localPrices={
      version:"sfdc-2026-krw-process-prices-v1",
      source:"SFDC_AUTHENTICATED_READ_ONLY_KRW_PROCESS_LINES",
      generated_at:new Date().toISOString(),salesforce_write_performed:false,
      records:[{
       source_kind:"VERIFIED_SFDC_KRW_PROCESS_PRICE",source_verified:true,
       created_date:"2026-10-01",quote_id:"QID-2026-10-01-123456",
       active:true,approval_status:"APPROVED",currency:"KRW",was_usd_converted:false,
       vat_basis:"VAT_EXCLUDED",account_id:"001000000000AAA",contact_id:"003000000000AAA",
       process_id:"Process-2026-01-01-00001",product_signature:"e".repeat(64),
       unit_price_krw:"300000",data_unit:"G raw data",data_size:"6",sample_quantity:48,
       product_name:"Synthetic RNA",process_name:"Sequencing by data amount"
      }]
    };
    await page.locator("#krw-local-file").setInputFiles({name:"synthetic-krw.json",
       mimeType:"application/json",buffer:Buffer.from(JSON.stringify(localPrices))});
    await page.locator("#krw-product").selectOption("e".repeat(64));
    await page.locator("#krw-process").selectOption("Process-2026-01-01-00001");
    await page.locator("#krw-account-id").fill("001000000000AAA");
    await page.locator("#krw-contact-id").fill("003000000000AAA");
    assert.match(await page.getByLabel("2026 KRW 가격 비교").innerText(),/300,000 KRW/);
    assert.match(await page.getByLabel("2026 KRW 가격 비교").innerText(),/재검증 필요/);
    await page.getByRole("button",{name:"비교 견적으로 선택"}).click();
    assert.match(await page.getByLabel("2026 KRW 가격 비교").innerText(),/COMPARISON_ONLY_REQUIRES_AUTHENTICATED_PRICE_RECHECK/);
    assert.equal(await page.getByRole("button",{name:/Salesforce 생성/}).isDisabled(),true);
    assert.equal(nonReadRequests.length,0,"General intake must not POST/PUT/PATCH/DELETE");
  } finally {
    if (page) await page.close();
    if (browser) await browser.close();
    if (server) server.kill();
  }
});
