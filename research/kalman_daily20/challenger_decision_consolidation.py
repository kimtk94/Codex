#!/usr/bin/env python3
"""Reconcile historical aggregate research reports; always RESEARCH_HOLD.

This is a consistency check, not an independent source or timestamp audit,
not a new statistical test, not a prospective evaluation or approval.
No network, credentials, order APIs, publication or scheduling.
"""
import argparse
import json
import math
from pathlib import Path

from challenger_prequential import load_protocol, parse, sha, require, PRIMARY, CONTROL
from challenger_archive_audit import PINS, PROTOCOL, CUTOFF

NAMES=tuple(f"{c}_{b}" for c in (20,16) for b in (30,50))
BLOCKS=(5,20,60)
ROLES={
    "rehearsal": "HISTORICAL_REHEARSAL_NOT_FORWARD",
    "benchmark": "RETROSPECTIVE_RESEARCH_HOLD",
    "execution": "RETROSPECTIVE_EXECUTION_RESEARCH_HOLD",
    "quote": "RETROSPECTIVE_RESEARCH_HOLD",
    "factor": "RETROSPECTIVE_RESEARCH_HOLD",
    "exclusion": "RETROSPECTIVE_RESEARCH_HOLD",
}


def guard(d,role):
    require(d["status"]==ROLES[role] and d["research_only"] is True
            and d["approved_live"] is False and d["source_finality_certified"] is False
            and type(d["forward_signals_created"]) is int and d["forward_signals_created"]==0
            and d["protocol_sha256"]==PROTOCOL
            and d["source_data_sha256"]==PINS["source_data"]["sha"]
            and d["source_research_sha256"]==PINS["source_research"]["sha"]
            and d["sessions"]==727,"DECISION_REPORT_SCOPE:"+role)


def equal(a,b):
    require(type(a) in (float,int) and type(b) in (float,int)
            and math.isfinite(a) and math.isfinite(b)
            and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-8),
            "DECISION_METRIC_MISMATCH")


def parity(x,y):
    for k in ("total_return","eod_mdd","trades"):
        equal(x[k],y[k])


def family(rows,expected,keys,pcol,hcol):
    require(len(rows)==expected*3,"DECISION_TEST_COUNT")
    out={}
    seen=None
    for block in BLOCKS:
        batch=[r for r in rows if r["block"]==block]
        ids={tuple(r[k] for k in keys) for r in batch}
        require(len(ids)==len(batch)==expected and (seen is None or ids==seen),
                "DECISION_TEST_FAMILY")
        seen=ids
        for r in batch:
            for col in (pcol,hcol):
                v=r[col]
                require(type(v) in (float,int) and math.isfinite(v) and 0<=v<=1,
                        "DECISION_INVALID_P")
        out[str(block)]=dict(tests=expected,
            bootstrap_holm_pass=sum(r[pcol]<.05 for r in batch),
            hac_holm_pass=sum(r[hcol]<.05 for r in batch),
            min_bootstrap_holm=min(r[pcol] for r in batch))
    return out


def consolidate(p,h,reports,digests):
    require(h==PROTOCOL and p["retrospective_cutoff_session"]==CUTOFF
            and p["primary"]["candidate"]==PRIMARY and p["primary"]["comparator"]==CONTROL
            and p["primary"]["looks"]==[126,252,504]
            and p["primary"]["alpha_by_look"]=={"126":0,"252":.02,"504":.03}
            and p["primary"]["formal_promotion"] is False,
            "DECISION_PROTOCOL_CHANGED")
    require(set(reports)==set(digests)==set(ROLES),"DECISION_REPORT_SET")
    for role,d in reports.items():
        guard(d,role)
    r,b,e,q,f,x=(reports[k] for k in ROLES)
    require(r["last_session"]==CUTOFF and r["first_session"]=="2024-01-02"
            and set(r["scenarios"])=={f"{n}_{k}" for n in NAMES for k in ("K1","K3","K1+K3")},
            "DECISION_REHEARSAL_SET")
    require(e["actual_quote_fills_verified"] is False
            and q["actual_quote_fills_verified"] is False and q["real_quotes_measured"]==0
            and e["supplied_intraday_symbols"]==0,
            "DECISION_PUBLIC_REPLAY_NOT_QUOTE_PROOF")
    require(e["union"]["unique_windows"]==q["request_counts"]["full_windows"]==193
            and e["union"]["required_symbol_days"]==q["request_counts"]["full_symbol_days"]==769
            and e["union"]["required_15m_bars"]==q["request_counts"]["full_expected_regular_bars"]==19946
            and e["union"]["supplied_complete_unique_windows"]==0,
            "DECISION_COVERAGE_PARITY")
    summary={}
    excluded_count=0
    for n in NAMES:
        s=n+"_K1+K3"
        base=r["scenarios"][s]
        bb=b["results"][s]
        ee=e["scenarios"][s]["additional_slippage_per_side_bp"]["0"]
        qq=q["scenarios"][s]["hypothetical_adverse_ask"]["0"]
        ff=f["results"][n]
        xx=x["results"][n]
        for z in (bb["strategy"],ee,qq,xx["BASE"]):
            parity(base,z)
        equal(ff["accounting"]["net_pnl"],100000*base["total_return"])
        equal(ff["EXPOSURE_M5"]["alpha_annual_arith_pct"],xx["BASE"]["alpha_annual_arith_pct"])
        equal(ff["EXPOSURE_M5"]["prior_fit_residual_annual_pct"]["2026"],
              xx["BASE"]["prior_fit_2026_alpha_pct"])
        excluded_count+=len(xx)-1
        summary[n]=dict(net_total_return=base["total_return"],eod_mdd=base["eod_mdd"],
            trades=base["trades"],annual_sharpe=bb["strategy"]["annualized_sharpe_zero_rate"],
            annual_returns=bb["strategy"]["annual_returns"],
            avg_open_exposure=bb["strategy"]["avg_open_exposure"],
            avg_close_exposure=bb["strategy"]["avg_close_exposure"],
            same_realized_vol_spy_return=bb["benchmarks"]["SPY_VOL"]["total_return"],
            same_realized_vol_qqq_return=bb["benchmarks"]["QQQ_VOL"]["total_return"],
            exposure_proxy_alpha_annual_arith_pct=ff["EXPOSURE_M5"]["alpha_annual_arith_pct"],
            exposure_proxy_prior_fit_2026_pct=xx["BASE"]["prior_fit_2026_alpha_pct"],
            top3_excluded_return=xx["TOP3_PRIMARY"]["total_return"],
            semi_excluded_return=xx["GROUP_SEMI"]["total_return"],
            additional_20bp_each_side_stress=e["scenarios"][s]["additional_slippage_per_side_bp"]["20"],
            actual_quote_fills_verified=False)
    require(excluded_count==x["tests_per_block"]==91,"DECISION_EXCLUSION_COUNT")
    multiplicity={
        "benchmark":family(b["significance"],40,("scenario","benchmark"),"p_holm","p_hac_holm"),
        "factor":family(f["significance"],16,("scenario","model"),"bootstrap_holm","hac_holm"),
        "exclusion":family(x["significance"],91,("scenario","exclusion"),"p_holm","hac_holm"),
    }
    return dict(version="kalman-challenger-decision-consolidation-v1",
        status="RESEARCH_HOLD",research_only=True,approved_live=False,approved_paper=False,
        activation_authorized=False,source_finality_certified=False,
        forward_signals_created=0,forward_evaluation="NOT_EVALUATED",
        historical_report_consistency="PASS",sessions=727,cutoff=CUTOFF,
        protocol_sha256=h,source_data_sha256=PINS["source_data"]["sha"],
        source_research_sha256=PINS["source_research"]["sha"],input_sha256=digests,
        primary=PRIMARY,control=CONTROL,fixed_looks=p["primary"]["looks"],
        alpha_by_look=p["primary"]["alpha_by_look"],cohorts=summary,
        retrospective_multiplicity=multiplicity,
        external_gates_not_assessed_by_this_cli=[
            "source_finality_26_of_26","deterministic_PIT_lineage","native_scheduler",
            "SIP_quote_basis_and_execution","independent_anchor_publication",
            "prospective_ledger_reexecution","external_review",
            "forward_economic_control","private_archive_authentication"],
        limitations=[
            "Internal aggregate consistency only; inputs from one historical source.",
            "No validation of external evidence or actual fills, no independent anchor retrieval.",
            "All comparisons retrospective; not an approval or new hypothesis selection.",
            "Do not change the frozen protocol or treat any PASS here as prospective eligibility."
        ])


def self_test():
    d=dict(status=ROLES["rehearsal"],research_only=True,approved_live=False,
           source_finality_certified=False,forward_signals_created=0,
           protocol_sha256=PROTOCOL,source_data_sha256=PINS["source_data"]["sha"],
           source_research_sha256=PINS["source_research"]["sha"],sessions=727)
    guard(d,"rehearsal")
    def reject(fn):
        try:
            fn()
        except (ValueError,KeyError):
            return
        raise AssertionError("DECISION_EXPECTED_REJECTION")
    reject(lambda:guard(dict(d,approved_live=True),"rehearsal"))
    reject(lambda:guard(dict(d,forward_signals_created=1),"rehearsal"))
    reject(lambda:guard(dict(d,protocol_sha256="0"*64),"rehearsal"))
    reject(lambda:guard(dict(d,status="PROSPECTIVE"),"rehearsal"))
    reject(lambda:equal(.1,.2))
    rows=[dict(block=k,id="a",p=.1,h=.2) for k in BLOCKS]
    require(family(rows,1,("id",),"p","h")["20"]["tests"]==1,"DECISION_TEST")
    reject(lambda:family(rows[:-1],1,("id",),"p","h"))
    reject(lambda:family(rows+[rows[0]],1,("id",),"p","h"))
    print("CHALLENGER_DECISION_CONSOLIDATION_SYNTHETIC_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    for k in (*ROLES,"out"):
        a.add_argument("--"+k)
    args=a.parse_args()
    if args.self_test:
        self_test()
        return
    require(all(getattr(args,k) for k in (*ROLES,"out")),"DECISION_INPUTS")
    reports,digests={},{}
    for role in ROLES:
        raw=Path(getattr(args,role)).read_bytes()
        reports[role]=parse(raw)
        digests[role]=sha(raw)
    p,h=load_protocol()
    result=consolidate(p,h,reports,digests)
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(status=result["status"],historical_report_consistency="PASS",
        forward_evaluation="NOT_EVALUATED",approved_live=False,approved_paper=False)))


if __name__=="__main__":
    main()
