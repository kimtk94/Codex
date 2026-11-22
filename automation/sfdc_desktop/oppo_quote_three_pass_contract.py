"""Offline three-pass SFDC snapshot / unsaved-form comparison contract.

All objects must be synthetic or redacted. Authenticated Salesforce operations
are not performed in CI. The UI runner must never click Save, Save & New,
Convert, Done for production records, or submit approvals/emails.
"""
from collections import Counter


class ValidationHold(ValueError):
    pass


def compare_three_snapshots(baseline, rounds, *, stable_columns=None):
    """Compare 3 repeated snapshots by stable record ID and displayed fields."""
    if not isinstance(baseline, dict) or not baseline:
        raise ValidationHold("Expected nonempty indexed baseline")
    if len(rounds) != 3:
        raise ValidationHold("Exactly three repeated snapshots required")
    result = []
    baseline_ids = set(baseline)
    for index, observed in enumerate(rounds, 1):
        if not isinstance(observed, dict):
            raise ValidationHold("Invalid snapshot structure")
        extra = sorted(set(observed) - baseline_ids)
        missing = sorted(baseline_ids - set(observed))
        changed = []
        for record_id in baseline_ids.intersection(observed):
            if stable_columns is None:
                if observed[record_id] != baseline[record_id]:
                    changed.append(record_id)
            else:
                if any(
                    observed[record_id].get(col) != baseline[record_id].get(col)
                    for col in stable_columns
                ):
                    changed.append(record_id)
        result.append({
            "round": index,
            "matched_ids": len(set(observed).intersection(baseline_ids)),
            "missing_count": len(missing),
            "extra_count": len(extra),
            "changed_count": len(changed),
            "status": "PASS" if not missing and not extra and not changed else "HOLD",
        })
    return result


def compare_three_dryrun_forms(rounds, *, record_type, required_checks):
    """Validate unsaved Opportunity/Quotation UI rehearsals, not CRM commits."""
    if record_type not in ("Opportunity", "Quotation"):
        raise ValidationHold("Unsupported record type")
    if len(rounds) != 3:
        raise ValidationHold("Exactly three form rehearsals required")
    results = []
    for i, row in enumerate(rounds, 1):
        if row.get("record_type") != record_type:
            raise ValidationHold("Wrong CRM object in form rehearsal")
        if row.get("save_clicked") is not False:
            raise ValidationHold("Save is forbidden in dry-run")
        if row.get("save_and_new_clicked", False):
            raise ValidationHold("Save & New is forbidden in dry-run")
        if row.get("convert_clicked", False):
            raise ValidationHold("Convert is forbidden in dry-run")
        checks = row.get("checks")
        if not isinstance(checks, dict):
            raise ValidationHold("Missing comparison readback")
        failures = [key for key in required_checks if checks.get(key) is not True]
        results.append({
            "round": i,
            "status": "PASS" if not failures else "HOLD",
            "missing_or_failed_checks": failures,
            "checks_passed": len(required_checks) - len(failures),
            "required_count": len(required_checks),
        })
    return results


def summary(snapshot_comparisons, opportunity_comparisons, quote_comparisons):
    """Refuse 100% completion claims if any comparison has HOLD."""
    sections = {
        "data": snapshot_comparisons,
        "opportunity": opportunity_comparisons,
        "quotation": quote_comparisons,
    }
    counts = {name: Counter(x.get("status") for x in rows) for name, rows in sections.items()}
    return {
        "all_pass": all(counts[name].get("PASS", 0) == 3 for name in sections),
        "passed_rounds": {name: counts[name].get("PASS", 0) for name in sections},
        "held_rounds": {name: 3 - counts[name].get("PASS", 0) for name in sections},
    }
