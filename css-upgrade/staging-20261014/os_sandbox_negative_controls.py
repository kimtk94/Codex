#!/usr/bin/env python3
"""Synthetic-only negative tests for an OS-enforced disposable sandbox.
No production source/DB or credentials are mounted in the container.
"""
import os, socket, pathlib, tempfile, json
def denied(label,fn):
 try: fn()
 except (OSError,PermissionError) as e:
  print("ISOLATION_DENIAL_PASS",label,type(e).__name__,flush=True)
  return
 raise AssertionError("ISOLATION_DENIAL_FAILED_"+label)
denied("TCP_LOOPBACK",lambda:socket.create_connection(("127.0.0.1",1),timeout=1))
denied("PRODUCTION_SOURCE_ABSENT",lambda:pathlib.Path("/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py").read_bytes())
denied("PRODUCTION_DB_ABSENT",lambda:pathlib.Path("/home/taehoon/services/novogene-css/state/css_project_manager.sqlite3").read_bytes())
denied("ROOT_FILESYSTEM_READONLY",lambda:pathlib.Path("/root/css-canary-should-fail").write_text("x"))
assert not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
assert not os.environ.get("SSH_KEY")
assert not os.environ.get("SERVER_SSH_KEY")
with tempfile.TemporaryDirectory(dir="/tmp") as root:
 p=pathlib.Path(root)/"synthetic.sqlite3"
 p.write_bytes(b"synthetic")
 assert p.read_bytes()==b"synthetic"
 print("TEMPORARY_SYNTHETIC_WRITABLE_PASS",flush=True)
print("NO_CSS_MAIN_EXECUTED",True,flush=True)
print("SANDBOX_NEGATIVE_CONTROLS_PASS",True,flush=True)
