#!/usr/bin/env python3
"""Local, editable per-deal SFDC preview; writes current_deal.json only, never Salesforce.
Usage: py -3.12 automation/sfdc_desktop/deal_editor.py --values PATH
Open localhost URL printed by script; select Apply to write reviewed deal values.
"""
import argparse,json,re
from decimal import Decimal,InvalidOperation
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from html import escape

FIELD_KEYS=("Opportunity Name","Account Name","Main Contact","Amount","Close Date",
            "Service Line","Stage","Progress Description","Status")
def numeric(value):
 try:
  n=Decimal(str(value).replace(",",""))
  if not n.is_finite() or n<0:return None
  return n
 except InvalidOperation:return None
def calculate(q,p):
 try:
  qty=int(q)
  unit=numeric(p)
  if qty<=0 or unit is None:return None
  return qty*unit
 except (ValueError,TypeError):return None
def app(values_path):
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def respond(self,code,body,typ="text/html; charset=utf-8"):
   self.send_response(code);self.send_header("Content-Type",typ)
   self.send_header("Cache-Control","no-store");self.end_headers()
   self.wfile.write(body.encode("utf-8"))
  def do_GET(self):
   if self.path!="/":return self.respond(404,"Not found")
   d=json.loads(values_path.read_text(encoding="utf-8-sig"))
   historical=d.get("_historical_reference") or {}
   entries=[]
   for key in FIELD_KEYS:
    v=escape(str(d.get(key,"")),quote=True)
    hint=escape(str(historical.get(key,"")),quote=True)
    if key=="Progress Description":tag=f'<textarea name="{key}" rows="3">{escape(str(d.get(key,"")))}</textarea>'
    else:tag=f'<input name="{key}" value="{v}" placeholder="{hint}" />'
    if key=="Opportunity Name":
     ref_name=escape(str(historical.get(key,"")),quote=True)
     entries.append(f'<label>{escape(key)} {tag}</label><button type="button" id="copy-historical-name" data-reference="{ref_name}">기존 Opportunity 이름 불러오기</button>')
    else:entries.append(f'<label>{escape(key)} {tag}</label>')
   html="""<!doctype html><html lang="ko"><meta charset="utf-8"><title>SFDC Deal Editor</title>
   <style>body{font:15px system-ui;max-width:850px;margin:35px auto;padding:0 20px}
   label{display:block;margin:13px 0}input,textarea{display:block;width:100%;box-sizing:border-box;
   padding:10px;border:1px solid #999;border-radius:6px;font:inherit}button{padding:12px 20px}
   .help{color:#555;font-size:13px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}</style>
   <h2>SFDC 신규 거래 편집</h2><p class="help">회색 힌트는 기존 거래 참조값입니다.
   저장은 로컬 current_deal.json만 변경하며 Salesforce는 절대 저장하지 않습니다.</p>
   <div class="row"><label>샘플 수<input id="qty" type="number" min="1" step="1"></label>
   <label>샘플당 단가 (KRW)<input id="unit" type="number" min="0" step="1"></label></div>
   <button type="button" onclick="calc()">샘플 수량을 이름 및 Amount에 반영</button>
   <form method="post" action="/apply"><div id="fields">"""+"".join(entries)+"""</div>
   <button type="submit">JSON에 변경사항 적용</button></form>
   <script>
   const qty=document.getElementById('qty');
   const unit=document.getElementById('unit');
   const nameInput=document.querySelector('[name="Opportunity Name"]');
   const amountInput=document.querySelector('[name="Amount"]');
   const copyName=document.getElementById('copy-historical-name');
   if(copyName)copyName.addEventListener('click',()=>{
     const source=copyName.dataset.reference||'';
     if(!source)return;
     if(nameInput.value.trim() && !confirm('현재 Opportunity 이름을 기존 이름으로 바꾸시겠습니까?'))return;
     nameInput.value=source;
     nameBase=source;
     const idx=quantityIndex(source);
     if(idx>=0)qty.value=source.split('-')[idx];
     nameInput.focus();
   });
   // Apply quantity/name synchronization only when exactly one known service is present.
   const services=/(?:mRNA-Seq|ncRNA-Seq|RNA-Seq|WGS|WES|16S|metagenom(?:ics|e)|PacBio|Nanopore|LC-MS|Olink)/gi;
   let nameBase=nameInput.value||nameInput.placeholder||'';
   function quantityIndex(name){
     if((name.match(services)||[]).length!==1)return -1;
     const tokens=name.split('-');
     const candidates=[];
     for(let i=1;i<tokens.length-1;i++)
       if(/^\d+$/.test(tokens[i]))candidates.push(i);
     // Avoid guessing when a name contains more than one numeric-only token.
     return candidates.length===1?candidates[0]:-1;
   }
   function calc(){
     const q=Number(qty.value),p=Number(unit.value);
     if(!Number.isSafeInteger(q)||q<=0)return;
     const idx=quantityIndex(nameBase);
     if(idx>=0){
       const tokens=nameBase.split('-');
       tokens[idx]=String(q);
       nameInput.value=tokens.join('-');
       nameBase=nameInput.value;
     }
     if(unit.value!==''&&Number.isFinite(p)&&p>=0)
       amountInput.value=String(q*p);
   }
   qty.addEventListener('input',calc);
   unit.addEventListener('input',calc);
   nameInput.addEventListener('input',()=>{nameBase=nameInput.value});
   const originalIndex=quantityIndex(nameBase);
   if(originalIndex>=0)qty.value=nameBase.split('-')[originalIndex];
   </script></html>"""
   self.respond(200,html)
  def do_POST(self):
   if self.path!="/apply":return self.respond(404,"Not found")
   from urllib.parse import parse_qs
   try:
    length=int(self.headers.get("Content-Length","0"))
    if length<=0 or length>30000:return self.respond(413,"Invalid size","text/plain")
    d=json.loads(values_path.read_text(encoding="utf-8-sig"))
    posted=parse_qs(self.rfile.read(length).decode("utf-8"),keep_blank_values=True)
    updated={key:posted.get(key,[""])[0].strip() for key in FIELD_KEYS}
    for key in FIELD_KEYS:
     if len(updated[key])>1500:return self.respond(400,"Field too long","text/plain")
    if updated["Amount"]:
     n=numeric(updated["Amount"])
     if n is None:return self.respond(400,"Amount must be nonnegative numeric","text/plain")
     updated["Amount"]=format(n,"f")
    for key in FIELD_KEYS:d[key]=updated[key]
    values_path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    self.respond(200,"<meta charset='utf-8'><p>로컬 JSON 수정 완료. Salesforce 저장은 하지 않았습니다.</p><a href='/'>편집 화면으로</a>")
   except (ValueError,UnicodeError,json.JSONDecodeError):self.respond(400,"Invalid data","text/plain")
 return Handler
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--values",required=True)
 p.add_argument("--port",type=int,default=8765)
 a=p.parse_args()
 path=Path(a.values)
 if not path.is_file():p.error("Editable values JSON does not exist")
 if not (1024<=a.port<=65535):p.error("Invalid port")
 server=ThreadingHTTPServer(("127.0.0.1",a.port),app(path))
 print(f"EDIT: http://127.0.0.1:{a.port} (Ctrl+C to stop)")
 print("Changes affect local JSON only; Salesforce untouched.")
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=="__main__":main()
