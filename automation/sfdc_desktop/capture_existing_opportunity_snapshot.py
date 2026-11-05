#!/usr/bin/env python3
"""Fresh read-only existing Opportunity snapshot from authenticated local Chrome.

NO Salesforce Save, no lookup selection, no data modification. Captures three
existing field values through edit-form read + Cancel (never fill) and exact
Account/Main Contact Salesforce record links. Does NOT certify a prior Save.
Private identifiers, values and snapshot JSON remain on the Windows workstation.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from audit_existing_opportunity_no_save import SFDC_ROUTE, validate_preflight
from audit_existing_numeric_date_nochange import check_lookup_ids
from capture_existing_lookup_links import DOM_SCRIPT, validate_links
from make_existing_change_template import FIELDS, current_value
from related_quotation_bridge import BUSINESS, same_record

PROVENANCE = "Salesforce UI existing Opportunity snapshot; no Save attested"


def validate_snapshot(data):
    """Strict metadata and field completeness for a snapshot, NOT post-Save proof."""
    if not isinstance(data, dict):
        raise ValueError("Snapshot object required")
    if (data.get("source") != PROVENANCE
            or data.get("page_reload_invoked") is not True
            or data.get("post_save_attested") is not False
            or data.get("salesforce_save_performed") is not False
            or data.get("save_allowed") is not False):
        raise ValueError("Only read-only non-post-Save snapshot accepted")
    if not SFDC_ROUTE.fullmatch(
            "/lightning/r/Opportunity/" + str(data.get("opportunity_record_id") or "") + "/view"):
        raise ValueError("Valid Salesforce Opportunity ID required")
    if not BUSINESS.fullmatch(str(data.get("business_id_from_prior_report") or "")):
        raise ValueError("Previously verified business Opportunity ID required")
    fields = data.get("current_field_values")
    if not isinstance(fields, dict) or set(fields) != set(FIELDS):
        raise ValueError("Exactly Name, Amount and Close Date snapshot required")
    if any(not isinstance(x, str) or not x.strip() for x in fields.values()):
        raise ValueError("Empty current field cannot certify snapshot")
    for key, prefix in (("account_record_id", "001"), ("contact_record_id", "003")):
        value = data.get(key)
        if not isinstance(value, str) or not re.fullmatch(prefix + r"[A-Za-z0-9]{15}", value):
            raise ValueError("Exact native Account/Contact link required")
    return True


def compare_snapshots(before, after):
    """Pure drift detection. Matching snapshots never imply a prior Save succeeded."""
    validate_snapshot(before)
    validate_snapshot(after)
    if not same_record(before["opportunity_record_id"], after["opportunity_record_id"]):
        return "HOLD_DIFFERENT_OPPORTUNITY_RECORD"
    if before["business_id_from_prior_report"] != after["business_id_from_prior_report"]:
        return "HOLD_DIFFERENT_CACHED_BUSINESS_ID"
    if not (same_record(before["account_record_id"], after["account_record_id"])
            and same_record(before["contact_record_id"], after["contact_record_id"])):
        return "HOLD_LOOKUP_LINK_DRIFT"
    if before["current_field_values"] != after["current_field_values"]:
        return "HOLD_FIELD_VALUE_DRIFT"
    return "SNAPSHOTS_MATCH_NOT_PROOF_OF_SAVE"


def preflight(bridge, links):
    if (not isinstance(bridge, dict)
            or bridge.get("version") != "live-related-quote-report-bridge-v1"
            or bridge.get("status") != "VERIFIED_BY_LIVE_QUOTATION_REPORT"
            or bridge.get("identity_verified") is not True
            or bridge.get("save_allowed") is not False
            or bridge.get("salesforce_save_performed") is not False):
        raise ValueError("Previously verified no-Save Quotation bridge required")
    if not isinstance(links, dict) or links.get("account_contact_field_links_verified") is not True:
        raise ValueError("Previously verified Account/Contact links required")
    if (links.get("salesforce_save_performed") is not False
            or links.get("salesforce_save_allowed") is not False
            or not same_record(bridge.get("opportunity_record_id"),
                               links.get("opportunity_record_id"))
            or not BUSINESS.fullmatch(str(bridge.get("business_opportunity_id") or ""))):
        raise ValueError("Opportunity identities disagree or no-Save proof missing")
    return True


def snapshot_browser(browser, bridge, links, reload_page=True):
    """Read authenticated current record after reload, requiring Cancel for all reads.

    A reload is deliberately performed only if no pre-existing editor is open;
    never silently discard another person's unsaved work.
    """
    preflight(bridge, links)
    if reload_page is not True:
        raise ValueError("Fresh page reload required")
    target = bridge["opportunity_record_id"]
    pages = []
    for context in browser.contexts:
        for page in context.pages:
            url = urlsplit(page.url)
            match = SFDC_ROUTE.fullmatch(url.path)
            if (url.hostname == "novogene.lightning.force.com"
                    and match and match.group(1) == target):
                pages.append(page)
    if len(pages) != 1:
        raise ValueError("Exactly one authenticated verified Opportunity page required")
    page = pages[0]
    validate_preflight(
        bridge, urlsplit(page.url).path,
        save_count=page.get_by_role("button", name="Save", exact=True).count(),
        cancel_count=page.get_by_role("button", name="Cancel", exact=True).count())
    page.reload(wait_until="domcontentloaded", timeout=30000)
    details = page.get_by_role("tab", name="Details", exact=True)
    details.wait_for(timeout=25000)
    if (urlsplit(page.url).hostname != "novogene.lightning.force.com"
            or not SFDC_ROUTE.fullmatch(urlsplit(page.url).path)
            or not same_record(target, SFDC_ROUTE.fullmatch(urlsplit(page.url).path).group(1))):
        raise RuntimeError("Reload changed target record or Salesforce host")
    if details.get_attribute("aria-selected") != "true":
        details.click(timeout=7000)
        page.wait_for_timeout(300)
    if (page.get_by_role("button", name="Save", exact=True).count()
            or page.get_by_role("button", name="Cancel", exact=True).count()):
        raise RuntimeError("Pre-existing edit after reload: abort safely")
    observed_links = validate_links(page.evaluate(DOM_SCRIPT))
    check_lookup_ids(links, page.evaluate(DOM_SCRIPT), target)

    fields = {}
    for field in FIELDS:
        if page.get_by_role("button", name="Save", exact=True).count():
            raise RuntimeError("Editor remained open before field read")
        fields[field] = current_value(page, field)  # Opens editor, reads, Cancel in finally.
        if page.get_by_role("button", name="Save", exact=True).count():
            raise RuntimeError("Editor remained open after field Cancel")
    result = {
        "version": "sfdc-opportunity-reloaded-baseline-v1",
        "source": PROVENANCE,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "page_reload_invoked": True,
        "post_save_attested": False,
        "post_save_verification_status": "NOT_APPLICABLE_NO_EXTERNAL_SAVE_EVIDENCE",
        "opportunity_record_id": target,
        "business_id_from_prior_report": bridge["business_opportunity_id"],
        "business_id_freshly_reconfirmed_from_report": False,
        **observed_links,
        "current_field_values": fields,
        "salesforce_save_performed": False,
        "save_allowed": False,
    }
    validate_snapshot(result)
    return result


def require_private_output(filename):
    """Refuse customer snapshots outside the dedicated private workstation folder.

    Existing files, symlink parents, links at the output name, and GitHub
    worktree paths fail closed. The caller opens the returned path with mode x.
    """
    target = Path(filename).expanduser()
    private = Path.home() / ".sfdc_desktop"
    if not private.is_dir() or private.is_symlink():
        raise ValueError("Private local directory must already exist and not be linked")
    if (not target.is_absolute()
            or target.parent.resolve() != private.resolve()
            or not target.name.endswith("_PRIVATE.json")
            or target.name.startswith(".")
            or target.exists() or target.is_symlink()):
        raise ValueError("Refusing unsafe, existing or non-private snapshot output")
    return target


def main():
    p = argparse.ArgumentParser()
    root = Path.home() / ".sfdc_desktop"
    p.add_argument("--bridge", default=str(root / "verified_live_quotation_report_bridge.json"))
    p.add_argument("--links", default=str(root / "existing_lookup_record_ids_private.json"))
    p.add_argument("--output", default=str(root / "opportunity_reloaded_snapshot_PRIVATE.json"))
    p.add_argument("--compare-prior", default="")
    p.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = p.parse_args()
    if args.cdp_url != "http://127.0.0.1:9222":
        p.error("Only the authorized local Chrome CDP port is supported")
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    target = require_private_output(args.output)
    bridge, links = read(args.bridge), read(args.links)
    preflight(bridge, links)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(args.cdp_url, timeout=12000)
        result = snapshot_browser(browser, bridge, links)
    with target.open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
    print("FRESH OPPORTUNITY SNAPSHOT: VALID")
    print("NATIVE ACCOUNT / CONTACT LINKS: VERIFIED")
    print("FIELD COUNT:", len(result["current_field_values"]))
    if args.compare_prior:
        try:
            comparison = compare_snapshots(read(args.compare_prior), result)
        except ValueError:
            comparison = "HOLD_PRIOR_SNAPSHOT_INVALID"
        print("SNAPSHOT COMPARISON:", comparison)
    print("POST-SAVE VERIFICATION: NOT ATTESTED")
    print("SALESFORCE SAVE PERFORMED: FALSE")
    print("PRIVATE OUTPUT:", target)


if __name__ == "__main__":
    main()
