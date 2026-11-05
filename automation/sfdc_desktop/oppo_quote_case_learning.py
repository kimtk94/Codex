#!/usr/bin/env python3
"""Learn sanitized SFDC Opportunity/Quotation naming patterns and apply current policy.

Sources: external, authenticated SFDC exports on the owner's workstation, never
stored in GitHub. Only aggregate statistics are returned. Historical case
patterns are evidence, not instructions to override current business rules.

Current owner rule: 250PE/PE250 is measured in M reads per sample; other
supported PE/SE sequencing modes are measured in Gb per sample.
No automatic reads<->Gb conversion. No price, contact, or quote enum guesses.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

MODE_TOKEN = re.compile(r"(?<![A-Za-z0-9])(?:(PE|SE)\s*[- ]?(\d{2,3})|(\d{2,3})\s*[- ]?(PE|SE))(?![A-Za-z0-9])", re.I)
M_READS_TOKEN = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*M\s*(?:reads?|read\s*pairs?|clusters?)(?![A-Za-z0-9])", re.I)
GB_TOKEN = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*Gb(?![A-Za-z0-9])", re.I)
PMP_TOKEN = re.compile(r"(?<![A-Za-z0-9])PMP(?![A-Za-z0-9])", re.I)
MIXED_UNITS = "MIXED_UNITS_REVIEW"
MIXED_MODES = "MIXED_SEQUENCING_MODES_REVIEW"


def normalize_mode(value):
    """Accept PE250/250PE and only explicitly specified PE/SE read lengths."""
    if not isinstance(value, str):
        raise ValueError("Sequencing mode must be a string")
    cleaned = value.upper().replace(" ", "").replace("-", "")
    match = re.fullmatch(r"(PE|SE)(\d{2,3})|(\d{2,3})(PE|SE)", cleaned)
    if not match:
        raise ValueError("Unknown sequencing mode: must be PE/SE plus read length")
    platform = match.group(1) or match.group(4)
    length = int(match.group(2) or match.group(3))
    if length < 30 or length > 300:
        raise ValueError("Read length outside supported review range")
    return platform + str(length)


def operational_depth_unit(mode):
    """Return the owner's current policy, not a learned historical majority."""
    return "M reads" if normalize_mode(mode) == "PE250" else "Gb"


def modes_in_case(value):
    return {
        normalize_mode(match.group(0))
        for match in MODE_TOKEN.finditer(str(value or ""))
    }


def observed_units(value):
    text = str(value or "")
    units = set()
    if M_READS_TOKEN.search(text):
        units.add("M reads")
    if GB_TOKEN.search(text):
        units.add("Gb")
    return units


def classify_case(value):
    """Extract a conservative, non-identifying pattern label from an Oppo/Quote name."""
    modes = modes_in_case(value)
    units = observed_units(value)
    pmp = bool(PMP_TOKEN.search(str(value or "")))
    if len(modes) > 1:
        status = MIXED_MODES
    elif len(units) > 1:
        status = MIXED_UNITS
    elif not modes:
        status = "MODE_UNDETERMINED"
    elif not units:
        status = "UNIT_UNDETERMINED"
    elif next(iter(units)) == operational_depth_unit(next(iter(modes))):
        status = "CURRENT_POLICY_ALIGNED"
    else:
        status = "HISTORICAL_UNIT_CONFLICT_REVIEW"
    return {
        "status": status,
        "modes": sorted(modes),
        "observed_units": sorted(units),
        "pmp": pmp,
        # No raw customer name, quote number, Opportunity ID or email here.
    }


def summarize_case_pairs(rows):
    """Summarize live SFDC Quote Export-like rows without copying customer data.

    rows: dictionaries with Quote Name / Opportunity Name fields. Supports
    standard export column names, never writes raw rows or raw snippets.
    """
    tally = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        quote = str(row.get("Quotation Name") or "")
        opp = str(row.get("Opportunity Name") or "")
        if not quote and not opp:
            continue
        tally["source_rows"] += 1
        for category, name in (("quote", quote), ("opportunity", opp)):
            if not name:
                tally[category + "_missing"] += 1
                continue
            sample = classify_case(name)
            tally[category + "_" + sample["status"]] += 1
            if sample["pmp"]:
                tally[category + "_pmp_cases"] += 1
            if sample["modes"] == ["PE250"]:
                tally[category + "_pe250_cases"] += 1
                tally[category + "_pe250_" + sample["status"]] += 1
        q = classify_case(quote) if quote else None
        o = classify_case(opp) if opp else None
        if q and o and "PE250" in q["modes"] and "PE250" in o["modes"]:
            if q["observed_units"] == o["observed_units"] and q["observed_units"]:
                tally["pe250_quote_opportunity_same_units"] += 1
            elif q["observed_units"] != o["observed_units"]:
                tally["pe250_quote_opportunity_unit_disagreement"] += 1
    return dict(sorted(tally.items()))



def suggest_pmp_sample_count_from_name(value):
    """Untrusted sample-count hint from a single-service Opportunity/Quote name.

    Observed historical pattern often has '-<count>-PMP-'. If the name has
    multiple PMP services or no literal count immediately before PMP, do not
    guess. This hint is never the authoritative new Opportunity sample count.
    """
    tokens = [part.strip() for part in str(value or "").split("-")]
    locations = [i for i, token in enumerate(tokens) if token.upper() == "PMP"]
    if len(locations) != 1:
        return {"status": "HOLD_AMBIGUOUS_PMP_SERVICES", "candidate": None}
    index = locations[0]
    if index == 0 or not re.fullmatch(r"[1-9]\d{0,2}", tokens[index - 1]):
        return {"status": "HOLD_SAMPLE_COUNT_NOT_EXPLICIT", "candidate": None}
    count = int(tokens[index - 1])
    if count > 500:
        return {"status": "HOLD_SAMPLE_COUNT_OUT_OF_SCOPE", "candidate": None}
    return {
        "status": "HINT_ONLY_CONFIRM_AGAINST_CONTACT_AND_NEW_REQUEST",
        "candidate": count,
    }


def validate_request_draft(draft):
    """Require explicit depth quantity and prohibit accidental M-reads/Gb mixing."""
    expected = {
        "contact_email", "service", "sequencing_mode",
        "sample_count", "depth_per_sample", "depth_unit",
    }
    if not isinstance(draft, dict) or set(draft) != expected:
        raise ValueError("Exactly six draft fields are required")
    if draft["service"] != "PMP":
        raise ValueError("Current pilot only supports explicit PMP requests")
    email = draft["contact_email"]
    if not isinstance(email, str) or not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}", email):
        raise ValueError("Exactly one contact email required")
    count = draft["sample_count"]
    if type(count) is not int or not 1 <= count <= 500:
        raise ValueError("Sample count must be an integer from 1 to 500")
    depth = draft["depth_per_sample"]
    if type(depth) not in (int, float) or not 0 < depth <= 100000:
        raise ValueError("Valid numeric depth per sample required")
    if draft["depth_unit"] != operational_depth_unit(draft["sequencing_mode"]):
        raise ValueError("Depth unit conflicts with the current mode-specific rule")
    if not isinstance(draft["sequencing_mode"], str):
        raise ValueError("Explicit sequencing mode required")
    return {
        "version": "oppo-quote-pmp-web-draft-v1",
        "status": "DRAFT_REQUIRES_CONTACT_ACCOUNT_AND_QUOTE_REVIEW",
        "service": "PMP",
        "sequencing_mode": normalize_mode(draft["sequencing_mode"]),
        "sample_count": count,
        "depth_per_sample": depth,
        "depth_unit": draft["depth_unit"],
        "total_nominal_depth": count * depth,
        "total_nominal_depth_unit": draft["depth_unit"],
        "reads_basis": "UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS",
        "contact_email": email,  # private draft only, not a GitHub Action input
        "account_id_verified": False,
        "contact_id_verified": False,
        "quotation_picklists_verified": False,
        "price_verified": False,
        "salesforce_save_allowed": False,
        "opportunity_created": False,
        "quotation_created": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--historical-csv", required=True,
                   help="Private locally exported SFDC Quote Export CSV")
    a = p.parse_args()
    with Path(a.historical_csv).open(encoding="utf-8-sig", newline="") as f:
        summary = summarize_case_pairs(csv.DictReader(f))
    print(json.dumps({
        "version": "oppo-quote-case-learning-summary-v1",
        "private_source_data_exported": False,
        "records_are_historical": True,
        "current_rule_pe250": "M reads/sample",
        "current_rule_other": "Gb/sample",
        "counts": summary,
    }, sort_keys=True, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
