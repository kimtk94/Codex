#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qq_historical_invoice_backfill import resolve_uidvalidity

class Fake:
    def __init__(self,response,status):
        self.r=response
        self.s=status
        self.calls=[]
    def response(self,name):
        return self.r
    def status(self,folder,arg):
        self.calls.append((folder,arg))
        return self.s

assert resolve_uidvalidity(Fake(("OK",[b"9876"]),("NO",[])),"INBOX")=="9876"
f=Fake(("OK",[None]),("OK",[b'INBOX (MESSAGES 12 UIDVALIDITY 123456)']))
assert resolve_uidvalidity(f,"INBOX")=="123456"
assert f.calls==[('"INBOX"','(UIDVALIDITY)')]
try:
    resolve_uidvalidity(Fake(("OK",[None]),("NO",[])),"INBOX")
except RuntimeError as e:
    assert "UIDVALIDITY_UNAVAILABLE_AFTER_STATUS" in str(e)
else:
    raise AssertionError("Fail-closed behavior missing")
print("QQ_UIDVALIDITY_TEST_PASS")
