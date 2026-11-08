#!/usr/bin/env python3
"""CSS freshness policy contract: static audit and fail-closed classification.

No external auth, no source calls, no CRM/Feishu mutations. A green CI here only
proves the policy contract; live source-to-sink parity is checked elsewhere.
"""
import datetime as dt
import json
import pathlib
import sys

POLICY_FILE = pathlib.Path(__file__).with_name("css_freshness_policy.json")
DOMAIN_IDS = frozenset({
    "mail", "lead", "quote", "contract_po", "sif_project",
    "invoice", "payment_revenue", "feishu_bi", "monitor",
})
STATUSES = frozenset({
    "PASS", "NO_NEW_DATA", "STALE", "SOURCE_UNAVAILABLE", "SINK_LAG", "BLOCK",
})
FIELDS = frozenset({
    "source_event_at", "source_probe_at", "ingest_at", "sink_readback_at",
    "verified_at", "source_identity", "source_count", "sink_count",
    "gap_count", "source_ref", "sink_ref", "run_url",
})


def validate_policy(data):
    if set(data.get("status_enum", [])) != STATUSES:
        raise ValueError("STATUS_ENUM_DRIFT")
    if not FIELDS.issubset(data.get("required_evidence", [])):
        raise ValueError("EVIDENCE_CONTRACT_INCOMPLETE")
    if "Vercel excluded" not in data.get("scope", ""):
        raise ValueError("SCOPE_DRIFT")
    domains = data.get("domains")
    if not isinstance(domains, list) or len(domains) != len(DOMAIN_IDS):
        raise ValueError("DOMAIN_COUNT_INVALID")
    if {d.get("id") for d in domains} != DOMAIN_IDS:
        raise ValueError("DOMAIN_IDS_INVALID")
    for domain in domains:
        checks = domain.get("checks")
        if not isinstance(checks, list) or len(checks) != 2:
            raise ValueError("DUAL_CROSSCHECK_REQUIRED:" + str(domain.get("id")))
        if {x.get("axis") for x in checks} != {"source", "sink"}:
            raise ValueError("INDEPENDENT_AXES_REQUIRED:" + str(domain.get("id")))
        if not domain.get("workflow") or not domain.get("name"):
            raise ValueError("WORKFLOW_OR_NAME_MISSING")
        for check in checks:
            if len(str(check.get("rule", "")).strip()) < 20:
                raise ValueError("CHECK_RULE_TOO_SHORT:" + str(domain.get("id")))
    return True


def parse_time(value):
    if isinstance(value, dt.datetime):
        t = value
    elif isinstance(value, str):
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("TIMESTAMP_MISSING")
    if t.tzinfo is None:
        raise ValueError("TIMESTAMP_TZ_REQUIRED")
    return t.astimezone(dt.timezone.utc)


def classify(obs, *, now, max_probe_age_hours):
    """Safe classification of supplied actual probe/readback evidence.

    The supplied max age MUST be derived from the upstream's cadence, not
    a universal daily value. Old last-event date is not alone an error.
    """
    if obs.get("source_probe_ok") is False:
        return "SOURCE_UNAVAILABLE"
    if obs.get("source_probe_ok") is not True:
        return "BLOCK"
    if (isinstance(max_probe_age_hours, bool)
            or not isinstance(max_probe_age_hours, (int, float))
            or not 0 < max_probe_age_hours < float("inf")):
        return "BLOCK"
    try:
        now_at = parse_time(now)
        probe_at = parse_time(obs.get("source_probe_at"))
    except (TypeError, ValueError, OverflowError):
        return "BLOCK"
    if probe_at > now_at:
        return "BLOCK"
    if now_at - probe_at > dt.timedelta(hours=max_probe_age_hours):
        return "STALE"
    if obs.get("sink_readback_ok") is False:
        return "SINK_LAG"
    if obs.get("sink_readback_ok") is not True:
        return "BLOCK"
    try:
        ingested_at = parse_time(obs.get("ingest_at"))
        sink_at = parse_time(obs.get("sink_readback_at"))
    except (TypeError, ValueError, OverflowError):
        return "BLOCK"
    if ingested_at > now_at or sink_at > now_at:
        return "BLOCK"
    if sink_at < ingested_at:
        return "SINK_LAG"
    delta, gap = obs.get("source_delta_count"), obs.get("gap_count")
    if type(delta) is not int or type(gap) is not int or delta < 0 or gap < 0:
        return "BLOCK"
    if gap > 0:
        return "SINK_LAG"
    if obs.get("identity_parity") is not True or obs.get("value_parity") is not True:
        return "BLOCK"
    return "NO_NEW_DATA" if delta == 0 else "PASS"


if __name__ == "__main__":
    if sys.argv[1:] != ["validate"]:
        sys.exit("usage: css_freshness_policy.py validate")
    validate_policy(json.loads(POLICY_FILE.read_text(encoding="utf-8")))
    print("CSS_FRESHNESS_POLICY_VALID=YES DOMAINS=9 CROSSCHECKS=18 LIVE_VERIFIED=NO")
