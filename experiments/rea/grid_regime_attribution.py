#!/usr/bin/env python3
"""Offline regime attribution on the unchanged grid V3 simulator. Never imports LIVE."""
from pathlib import Path

POLICIES=("baseline","inhibit_new_buys","cancel_resting_buys","reseed_on_up")

def build(source,policy):
    if policy not in POLICIES: raise ValueError(policy)
    if policy=="baseline":
        # Read-only counters injected into the unchanged reference decisions.
        changes=[
          (" orders={};fills=ambiguous=gaps=0;fees=0.;peak=capital;mdd=0.;turnover=0.",
           " orders={};fills=ambiguous=gaps=0;fees=0.;peak=capital;mdd=0.;turnover=0.;exposure_sum=0.;exposure_n=0;exposure_max=0."),
          ("  if min(krw,eth,hold_krw,hold_eth)<-1e-5:raise RuntimeError(\"balance invariant\")",
           """  if min(krw,eth,hold_krw,hold_eth)<-1e-5:raise RuntimeError("balance invariant")
  exposure=(eth+hold_eth)*close/(krw+hold_krw+(eth+hold_eth)*close)
  exposure_sum+=exposure;exposure_n+=1;exposure_max=max(exposure_max,exposure)"""),
          (" return dict(year=y,spacing_pct=",
           " return dict(exposure_mean_pct=round(100*exposure_sum/max(exposure_n,1),4),exposure_max_pct=round(100*exposure_max,4),measured_bars=exposure_n,year=y,spacing_pct="),
        ]
        for old,new in changes:
            if source.count(old)!=1:raise RuntimeError("BASELINE_MEASUREMENT_PATCH_MISMATCH "+old[:60])
            source=source.replace(old,new,1)
        return source
    replacements=[
      (" seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor",
       " seed(anchor);prev=dt.datetime.fromisoformat(first[0]);last=anchor;prior_regime=None;policy_violations=0;gap_buy_violations=0"),
      ("   gaps+=1;cancel();seed(close)",
       """   gaps+=1;cancel();seed(close)
   # Gap candle cannot infer fills. Apply regime gate immediately after reseed.
   rg=regimes.get(t.astimezone(kst).date(),'WARMUP')
   if rg!='UP':
    for key in list(orders):
     if key[0]=='B':
      v=orders.pop(key);krw+=v*(1+fee);hold_krw-=v*(1+fee)
   gap_buy_violations+=sum(1 for side,p in orders if side=='B') if rg!='UP' else 0"""),
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
       " return dict(policy_violations=policy_violations,gap_buy_violations=gap_buy_violations,year=y,spacing_pct="),
    ]
    # On a data gap all prior orders are invalidated, so DOWN gap reseeding
    # keeps only sells even for inhibit_new_buys. On contiguous bars existing
    # buys remain live for that policy; other policies cancel them.
    # Measurement-only counters: no order or cash mutation.
    replacements.extend([
      (" orders={};fills=ambiguous=gaps=0;fees=0.;peak=capital;mdd=0.;turnover=0.",
       " orders={};fills=ambiguous=gaps=0;fees=0.;peak=capital;mdd=0.;turnover=0.;exposure_sum=0.;exposure_n=0;exposure_max=0.;down_bars=0"),
      ("  if min(krw,eth,hold_krw,hold_eth)<-1e-5:raise RuntimeError(\"balance invariant\")",
       """  if min(krw,eth,hold_krw,hold_eth)<-1e-5:raise RuntimeError("balance invariant")
  exposure=(eth+hold_eth)*close/(krw+hold_krw+(eth+hold_eth)*close)
  exposure_sum+=exposure;exposure_n+=1;exposure_max=max(exposure_max,exposure)
  if rg!='UP':down_bars+=1"""),
      (" return dict(policy_violations=policy_violations,gap_buy_violations=gap_buy_violations,year=y,spacing_pct=",
       " return dict(exposure_mean_pct=round(100*exposure_sum/max(exposure_n,1),4),exposure_max_pct=round(100*exposure_max,4),measured_bars=exposure_n,down_bars=down_bars,policy_violations=policy_violations,gap_buy_violations=gap_buy_violations,year=y,spacing_pct="),
    ])
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
