#!/usr/bin/env python3
"""Offline regime attribution on the unchanged grid V3 simulator. Never imports LIVE."""
from pathlib import Path

POLICIES=("baseline","inhibit_new_buys","cancel_resting_buys","reseed_on_up")

def build(source,policy):
    if policy not in POLICIES: raise ValueError(policy)
    if policy=="baseline": return source
    replacements=[
      (" seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor",
       " seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor;prior_regime=None;policy_violations=0"),
      ("   gaps+=1;cancel();seed(close)",
       """   gaps+=1;cancel();seed(close)
   # Gap candle cannot infer fills. Apply regime gate immediately after reseed.
   rg=regimes.get(t.astimezone(kst).date(),'WARMUP')
   if rg!='UP':
    for key in list(orders):
     if key[0]=='B':
      v=orders.pop(key);krw+=v*(1+fee);hold_krw-=v*(1+fee)"""),
      ("  prev=t\n  bs=[key for key in orders",
       """  prev=t
  rg=regimes.get(t.astimezone(kst).date(),'WARMUP')
  if rg!='UP' and policy in ('cancel_resting_buys','reseed_on_up'):
   for key in list(orders):
    if key[0]=='B':
     v=orders.pop(key);krw+=v*(1+fee);hold_krw-=v*(1+fee)
  if policy=='reseed_on_up' and rg=='UP' and prior_regime!='UP':
   cancel();seed(close)
  prior_regime=rg
  if rg!='UP' and policy in ('cancel_resting_buys','reseed_on_up'):
   policy_violations+=sum(1 for side,p in orders if side=='B')
  bs=[key for key in orders"""),
      ("   for side,px,amount in pending:add(side,px,amount)",
       """   for side,px,amount in pending:
    if side!='B' or rg=='UP':add(side,px,amount)"""),
      (" return dict(year=y,spacing_pct=",
       " return dict(policy_violations=policy_violations,year=y,spacing_pct="),
    ]
    # Inhibit buys does not cancel resting bids, but disables replacement buys.
    if policy=="inhibit_new_buys":
      replacements[2]=(replacements[2][0],replacements[2][1])
    generated=source
    for old,new in replacements:
      if generated.count(old)!=1:raise RuntimeError("SOURCE_PATCH_MISMATCH "+old[:64])
      generated=generated.replace(old,new,1)
    return generated

def simulate(source,con,year,spacing,levels,capital,fee,regimes,kst,policy):
    code=build(source,policy)
    ns={"__name__":"grid_attribution","__file__":"<in-memory>","regimes":regimes,"kst":kst,"policy":policy}
    exec(compile(code,"<grid-attribution>","exec"),ns)
    return ns["sim"](con,year,spacing,levels,capital,fee)
