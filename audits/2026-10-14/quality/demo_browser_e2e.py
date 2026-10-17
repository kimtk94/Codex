"""Chromium Playwright demo-only E2E: no deployment and no external egress.

The demo bundle is materialized only to a temporary local directory. The
browser context aborts all network requests except 127.0.0.1 loopback, and the
server serves only the generated 30-file static demo (no credential access).
"""
from __future__ import annotations
import asyncio
import json
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from build_demo_only_staging import create, MARKER

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def do_POST(self):
        self.send_error(405)

async def check(root:Path, port:int):
    from playwright.async_api import async_playwright
    results=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        try:
            for name,viewport in [
                ("desktop",{"width":1365,"height":768}),
                ("mobile",{"width":390,"height":844}),
            ]:
                context=await browser.new_context(viewport=viewport,service_workers="block")
                blocked=[]
                attempts=[]
                async def route_handler(route):
                    url=route.request.url
                    parsed=urlparse(url)
                    if parsed.hostname!="127.0.0.1" or parsed.port!=port:
                        blocked.append(url.split("?",1)[0][:140])
                        await route.abort()
                    else:
                        attempts.append(parsed.path)
                        await route.continue_()
                await context.route("**/*",route_handler)
                page=await context.new_page()
                response=await page.goto(f"http://127.0.0.1:{port}/index.html",wait_until="networkidle")
                assert response and response.status==200,(name,"HTML_NOT_SERVED")
                assert await page.locator("#kalman-demo-isolation-banner").count()==0,(name,"LEGACY_BANNER_PRESENT")
                assert await page.locator(".demo-warning").count()==1,(name,"WARNING_NOT_VISIBLE")
                assert await page.locator(".demo-warning").is_visible(),(name,"WARNING_HIDDEN")
                assert "SYNTHETIC DEMO ONLY" in await page.locator(".demo-warning").inner_text()
                assert "NO CONNECTION" in await page.locator("#demo-environment").inner_text()
                assert "synthetic mock only" in await page.locator("#demo-health").inner_text()
                assert await page.locator("button").count()==0,(name,"UNEXPECTED_ACTION_BUTTON")
                assert await page.locator("input").count()==0,(name,"UNEXPECTED_CREDENTIAL_INPUT")
                assert not await page.locator("body").evaluate(
                    "(el) => /\b(buy now|sell now|place order)\b/i.test(el.innerText)"
                ),(name,"TRADING_ACTION_COPY_PRESENT")
                overflow=await page.evaluate(
                    "() => document.documentElement.scrollWidth > window.innerWidth + 2"
                )
                assert not overflow,(name,"HORIZONTAL_OVERFLOW")
                assert not blocked,(name,"UNEXPECTED_EXTERNAL_REQUEST",blocked)
                assert not any(x.startswith("/api/") for x in attempts),(name,"UNEXPECTED_API_REQUEST")
                # Exercise browser-level egress filter with a deliberately
                # generated HTTPS request that MUST be denied at route level.
                await page.evaluate("""async () => {
                    try { await fetch('https://example.invalid/demo-egress-test'); }
                    catch (_) { /* expected network abort */ }
                }""")
                assert len(blocked)==1,(name,"EGRESS_PROBE_NOT_BLOCKED",blocked)
                results.append({"viewport":name,"html_loaded":True,"notice_visible":True,
                                "network_before_probe":attempts,
                                "external_egress_probe_blocked":True,
                                "trading_controls":0,"credential_inputs":0,
                                "horizontal_overflow":False})
                await context.close()
        finally:
            await browser.close()
    return results

def main():
    files=create()
    with tempfile.TemporaryDirectory(prefix="kalman-demo-browser-") as tmp:
        root=Path(tmp)
        for name,data in files.items():
            dest=root/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
        handler=lambda *args,**kwargs: QuietHandler(*args,directory=str(root),**kwargs)
        server=ThreadingHTTPServer(("127.0.0.1",0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try: results=asyncio.run(check(root,server.server_port))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
    print(json.dumps({"status":"CHROMIUM_DEMO_ONLY_E2E_PASS",
                      "viewports":results,
                      "live_broker_or_neon_used":False,
                      "deployed_to_vercel":False,"production_release_authorized":False},
                     ensure_ascii=False))
if __name__=="__main__": main()
