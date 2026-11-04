/** Synthetic-only browser smoke test. Never logs in to Salesforce or uses client data. */
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
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
    const localApiResponse = await page.evaluate(async () => {
      const response = await fetch("/api/sfdc/contact-candidates-local?name=" + encodeURIComponent("김민수"), {
        headers: {"X-SFDC-Local-Preview":"1"},cache:"no-store"
      });
      return response.status;
    });
    assert.equal(localApiResponse, 404, "Hosted/default web must disable private workstation source");
    const disabledPcReview = await fetch(base + "/api/sfdc/review-local", {
      method:"POST",
      headers:{
        "Content-Type":"application/json",
        "Origin":base,
        "Sec-Fetch-Site":"same-origin",
        "X-SFDC-Local-Preview":"1",
      },
      body:JSON.stringify({version:"synthetic-test",salesforce_save_allowed:false}),
    });
    assert.equal(disabledPcReview.status,404,
      "Hosted/default server must not expose authenticated workstation review");
    assert.equal(await page.locator("#sfdc-contact-email").inputValue(), "");
    assert.equal(await page.locator("#sfdc-mode").inputValue(), "PE250");
    assert.equal((await page.locator("#sfdc-depth + span").textContent()).trim(), "M reads");
    assert.equal(await page.getByRole("button", {name:"Salesforce 일괄 생성 · 연결 전"}).isDisabled(), true);

    await page.locator("#sfdc-mode").selectOption("PE150");
    assert.equal((await page.locator("#sfdc-depth + span").textContent()).trim(), "Gb");
    await page.locator("#sfdc-mode").selectOption("PE250");
    assert.equal((await page.locator("#sfdc-depth + span").textContent()).trim(), "M reads");

    const localRows = [
      {name:"김민수", institution:"서울대학교", contact_id:"003000000000001AAA",
       account_id:"001000000000001AAA",contact_email:"first@example.org",
       opportunity_ids:["006000000000001AAA"]},
      {name:"김민수", institution:"연세대학교", contact_id:"003000000000002AAA",
       account_id:"001000000000002AAA",contact_email:"second@example.org",
       opportunity_ids:["006000000000002AAA"]},
      {name:"김민수", institution:"한남대학교", contact_id:"003000000000003AAA",
       account_id:"001000000000003AAA",contact_email:"excluded@example.org",
       opportunity_ids:["006000000000003AAA"]},
    ];
    await page.locator("#sfdc-local-contact-file").setInputFiles({
      name:"authorized-private-synthetic.json",mimeType:"application/json",
      buffer:Buffer.from(JSON.stringify(localRows)),
    });
    await page.locator("#sfdc-contact-name").fill("김민수");
    const contactSelect=page.locator("#sfdc-contact-candidate");
    assert.equal(await contactSelect.locator("option").count(),3);
    await contactSelect.selectOption("003000000000002AAA|001000000000002AAA");
    assert.equal(await page.locator("#sfdc-contact-email").inputValue(),"second@example.org");
    assert.equal(nonReadRequests.length,0,"Contact import must remain browser-local");
    assert.equal(await page.getByLabel("선택한 Contact").count(),1);
    assert.match(await page.getByLabel("선택한 Contact").textContent(),/연세대학교/);
    await page.getByRole("button",{name:"검토용 명령서 생성"}).click();
    const reviewButton=page.getByRole("button",{name:"Contact ID 포함 · PC 검토 패킷 저장"});
    assert.equal(await reviewButton.isEnabled(),true);
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      reviewButton.click(),
    ]);
    assert.equal(download.suggestedFilename(),"sfdc-oppo-quote-contact-review-private.json");
    const packet=JSON.parse(await readFile(await download.path(),"utf8"));
    assert.equal(packet.selected_contact.contact_id,"003000000000002AAA");
    assert.equal(packet.selected_contact.account_id,"001000000000002AAA");
    assert.deepEqual(packet.selected_contact.opportunity_ids,["006000000000002AAA"]);
    assert.equal(packet.draft.request.contact_email,"second@example.org");
    assert.equal(packet.gate.salesforce_save_allowed,false);
    assert.equal(nonReadRequests.length,0,"Private packet must not make any CRM write requests");
    // A manually edited email invalidates the selected native Contact identity.


    await page.locator("#sfdc-contact-email").fill("researcher@example.org");
    await page.locator("#sfdc-samples").fill("5");
    await page.locator("#sfdc-depth").fill("1");
    await page.getByRole("button",{name:"검토용 명령서 생성"}).click();
    assert.equal(await page.getByRole("button",{name:"Contact ID 포함 · PC 검토 패킷 저장"}).isDisabled(),true);
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
