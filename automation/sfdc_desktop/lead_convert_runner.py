"""Guarded Salesforce Lead -> Contact -> CDMS runner.

Default mode is read-only. Only --execute permits live Salesforce writes.
Runs on an authorized desktop with a logged-in Chrome CDP session; never on CI.
Do not retry Convert after errors; first inspect the Lead and Contact records.
"""
from __future__ import annotations

import argparse
import re
from typing import Any

from lead_convert_policy import ACADEMIC_PI, build_contact_plan, build_form_name_plan, cdms_sync_verified, english_full_name

HOST = 'https://novogene.lightning.force.com'
LEAD_ID_RE = re.compile(r'^00Q[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$')
ACCOUNT_ID_RE = re.compile(r'^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$')


class ConversionStopped(ValueError):
    """Preflight or readback failed. Never blindly retry an uncertain write."""


def extract_billing_address(text: str) -> dict[str, str]:
    """Parse Salesforce billing address; HOLD for unknown formats."""
    found = re.search(r'(?m)^Billing Address\s*\n(?P<body>.*?)\nEdit Billing Address\b', text, re.S)
    if not found:
        raise ConversionStopped('Account Billing Address not verified')
    lines = [line.strip() for line in found['body'].splitlines() if line.strip()]
    if len(lines) != 3:
        raise ConversionStopped('Unsupported billing address format')
    city_zip = re.fullmatch(r'(.+?),\s*([0-9A-Za-z][0-9A-Za-z -]{2,14})', lines[1])
    if not city_zip:
        raise ConversionStopped('Unsupported city/postal code format')
    return dict(street=lines[0], city=city_zip[1].strip(), state='',
                postal_code=city_zip[2].strip(), country=lines[2])


def preflight_lead_text(body: str, *, expected_email: str, korean_name: str, convert_visible: bool) -> str:
    """Missing Convert is NOT evidence of conversion. Require linked Contact proof."""
    if not re.search(re.escape(expected_email), body, re.I):
        raise ConversionStopped('Lead email does not match')
    # Salesforce commonly renders the Lead name as "given-name surname".
    displayed = _following_field_value(body, 'Name')
    canonical = korean_name[0] + korean_name[1:]
    reversed_display = korean_name[1:] + ' ' + korean_name[0]
    if canonical not in body and displayed != reversed_display:
        raise ConversionStopped('Korean Lead name does not match')
    if not convert_visible or 'Your lead has been converted' in body:
        return 'needs_contact_verification'
    return 'ready'


def _following_field_value(text: str, label: str) -> str:
    """Read the next nonblank line below an exact Salesforce field label."""
    rows = [line.strip() for line in text.splitlines()]
    for index, value in enumerate(rows):
        if value == label:
            for candidate in rows[index + 1:index + 3]:
                if candidate:
                    return candidate
    return ''


def verify_prior_conversion(*, lead_body: str, contact_body: str,
                            expected_email: str, account_name: str,
                            expected_korean_name: str) -> str:
    """Verify independent Lead-to-Contact identity before declaring converted."""
    lead_business_id = _following_field_value(lead_body, 'SFDC Lead ID')
    if not re.fullmatch(r'Lead-\d{4}-\d{2}-\d{2}-\d+', lead_business_id):
        raise ConversionStopped('Valid Lead business ID not found')
    if _following_field_value(contact_body, 'Lead Converted ID') != lead_business_id:
        raise ConversionStopped('Contact not proven linked to the requested Lead')
    if expected_email.casefold() not in contact_body.casefold():
        raise ConversionStopped('Converted Contact email mismatch')
    if account_name not in contact_body:
        raise ConversionStopped('Converted Contact Account mismatch')
    if expected_korean_name not in contact_body:
        raise ConversionStopped('Converted Contact Korean name mismatch')
    return cms_id_from_view(contact_body)


def contact_id_from_url(url: str) -> str:
    """Return only a real Salesforce Contact record ID from a Contact URL."""
    match = re.search(
        r'/lightning/r/Contact/(003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/(?:view|edit)(?:[?]|$)',
        url,
    )
    return match.group(1) if match else ''


def require_redirected_contact_identity(
    *, contact_id: str, expected_contact_id: str, email: str,
    expected_email: str, korean_name: str, expected_korean_name: str,
    english_name: str, expected_english_name: str,
) -> None:
    """Fail closed when the Lead redirected to any unexpected Contact."""
    if not contact_id or contact_id != expected_contact_id:
        raise ConversionStopped('Lead redirected to an unexpected Contact ID')
    if email.strip().casefold() != expected_email.strip().casefold():
        raise ConversionStopped('Redirected Contact email mismatch')
    if korean_name.strip() != expected_korean_name.strip():
        raise ConversionStopped('Redirected Contact Korean name mismatch')
    if english_name.strip() != expected_english_name.strip():
        raise ConversionStopped('Redirected Contact English name mismatch')


def contact_id_from_success_links(links: list[tuple[str, str]]) -> str:
    for _label, href in links:
        match = re.fullmatch(
            r'/lightning/r/(?:Contact/)?(003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)/view', href or '')
        if match:
            return match[1]
    raise ConversionStopped('Converted Contact ID unavailable; do not reconvert')


def cms_id_from_view(text: str) -> str:
    found = re.search(r'(?m)^CMS Contact ID\s*\n\s*(CP[0-9]+)\s*\n', text)
    return found[1] if found else ''


def require_one_visible(locator: Any, field: str):
    if locator.count() != 1 or not locator.is_visible():
        raise ConversionStopped(f'Expected exactly one visible {field}')
    return locator


def read_account_address(page: Any, account_id: str, account_name: str) -> dict[str, str]:
    page.goto(f'{HOST}/lightning/r/Account/{account_id}/view', wait_until='domcontentloaded')
    page.get_by_text(account_name, exact=False).first.wait_for(timeout=20000)
    section = page.get_by_role('button', name='Address Information')
    if section.count() == 1 and section.get_attribute('aria-expanded') == 'false':
        section.click()
    # Lightning renders address fields asynchronously after the page header.
    page.get_by_role('button', name='Address Information').wait_for(timeout=20000)
    page.wait_for_timeout(400)
    if page.get_by_role('button', name='Edit Billing Address').count() == 0:
        raise ConversionStopped('Account Billing Address is empty or not available')
    body = page.locator('body').inner_text()
    if account_name not in body:
        raise ConversionStopped('Account name does not match Account ID')
    return extract_billing_address(body)


def verify_contact_readback(page: Any, contact_id: str, plan: Any) -> None:
    """Check persisted Contact values, not just Salesforce success toasts."""
    page.goto(f'{HOST}/lightning/r/Contact/{contact_id}/view', wait_until='domcontentloaded')
    edit = page.get_by_role('button', name='Edit', exact=True).first
    edit.wait_for(timeout=20000)
    edit.click()
    page.locator('input[name=firstName]').wait_for(timeout=20000)
    expected = dict(firstName=plan.first_name, lastName=plan.last_name,
                    city=plan.shipping_city, province=plan.shipping_state,
                    postalCode=plan.shipping_postal_code, country=plan.shipping_country)
    for field, value in expected.items():
        if page.locator(f'input[name={field}]').input_value() != value:
            raise ConversionStopped(f'Persisted Contact mismatch: {field}')
    if page.locator('textarea[name=street]').input_value() != plan.shipping_street:
        raise ConversionStopped('Persisted shipping street mismatch')
    if page.get_by_role('combobox', name='Org Type Group').inner_text().strip() != plan.org_type:
        raise ConversionStopped('Persisted Org Type Group mismatch')
    if page.get_by_role('combobox', name='Job Function').inner_text().strip() != plan.job_function:
        raise ConversionStopped('Persisted Job Function mismatch')
    page.get_by_role('button', name='Cancel', exact=True).last.click()
    page.get_by_role('button', name='Edit', exact=True).first.wait_for(timeout=20000)


def prepare_conversion_modal(page: Any, plan: Any, account_name: str) -> Any:
    """Populate Convert Lead UI without committing. Caller must Convert or Cancel.

    Tested against the authorized Salesforce Lightning 2026-11-05 modal.
    """
    require_one_visible(page.get_by_role('button', name='Convert', exact=True), 'Convert').click()
    modal = page.locator('[role=dialog]').filter(has_text='Convert Lead').last
    try:
        modal.get_by_text('Choose Existing Account', exact=True).wait_for(
            state='visible', timeout=15000)
        modal.get_by_text('Choose Existing Account', exact=True).click()
        modal.get_by_placeholder('Search for matching accounts').fill(account_name)
        choice = modal.get_by_text(account_name, exact=True)
        choice.wait_for(state='visible', timeout=15000)
        if choice.count() != 1:
            raise ConversionStopped('Account search not uniquely matched')
        choice.click()
        selected = 'Account Search - Current Selection: ' + account_name
        if selected not in modal.inner_text():
            raise ConversionStopped('Existing Account was not selected')
        contact_section = require_one_visible(
            modal.get_by_role('button', name='Contact', exact=True), 'Contact section')
        if contact_section.get_attribute('aria-expanded') == 'false':
            contact_section.click()
        require_one_visible(modal.get_by_label('First Name', exact=True), 'First Name').fill(
            plan.first_name)
        require_one_visible(modal.get_by_label('Last Name', exact=True), 'Last Name').fill(
            plan.last_name)
        checkbox = require_one_visible(
            modal.locator('input[aria-labelledby="checkbox input"]'),
            "Don't create an opportunity upon conversion",
        )
        if not checkbox.is_checked():
            label = require_one_visible(
                modal.locator('label[for="' + checkbox.get_attribute('id') + '"]'),
                'No-Opportunity checkbox label',
            )
            label.click()
        if not checkbox.is_checked():
            raise ConversionStopped('No-Opportunity checkbox failed to set')
        if modal.get_by_label('First Name', exact=True).input_value() != plan.first_name:
            raise ConversionStopped('Korean full-name field did not retain its value')
        if modal.get_by_label('Last Name', exact=True).input_value() != plan.last_name:
            raise ConversionStopped('English full-name field did not retain its value')
        return modal
    except Exception:
        if modal.count() and modal.get_by_role('button', name='Cancel', exact=True).count():
            modal.get_by_role('button', name='Cancel', exact=True).last.click()
        raise


def run(args: argparse.Namespace) -> dict[str, str]:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError  # deferred: no dependency in CI
    for pattern, value, label in (
        (LEAD_ID_RE, args.lead_id, 'Lead'),
        (ACCOUNT_ID_RE, args.account_id, 'Account'),
    ):
        if not pattern.fullmatch(value):
            raise ConversionStopped(f'Invalid {label} ID')
    if not args.email or not args.account_name:
        raise ConversionStopped('Exact email and Account name are required')
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        tabs = [page for ctx in browser.contexts for page in ctx.pages if 'lightning.force.com' in page.url]
        if not tabs:
            raise ConversionStopped('No authorized Salesforce session')
        page = tabs[0]
        page.goto(f'{HOST}/lightning/r/Lead/{args.lead_id}/view', wait_until='domcontentloaded')
        # Salesforce automatically redirects previously converted Leads to Contacts.
        try:
            page.wait_for_url(re.compile(
                r'/lightning/r/Contact/003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?/view'),
                timeout=10000,
            )
        except PlaywrightTimeoutError:
            pass  # Normal unconverted Lead: continue with Lead preflight.

        redirected_id = contact_id_from_url(page.url)
        if redirected_id:
            known = getattr(args, 'known_contact_id', None)
            if not known:
                raise ConversionStopped('Converted Lead redirect requires verified Contact ID')
            account_href = f'/lightning/r/Account/{args.account_id}/view'
            page.locator(f'a[href="{account_href}"]').first.wait_for(timeout=15000)
            page.get_by_text(args.account_name, exact=True).first.wait_for(timeout=15000)
            cms = cms_id_from_view(page.locator('body').inner_text())
            edit = page.get_by_role('button', name='Edit', exact=True).first
            edit.wait_for(timeout=20000)
            edit.click()
            page.locator('input[name=firstName]').wait_for(timeout=20000)
            try:
                require_redirected_contact_identity(
                    contact_id=redirected_id, expected_contact_id=known,
                    email=page.locator('input[name=Email]').input_value(),
                    expected_email=args.email,
                    korean_name=page.locator('input[name=firstName]').input_value(),
                    expected_korean_name=args.korean_name,
                    english_name=page.locator('input[name=lastName]').input_value(),
                    expected_english_name=english_full_name(args.surname, args.given),
                )
                expected_business_id = getattr(args, 'lead_business_id', None)
                if expected_business_id and _following_field_value(
                    page.locator('body').inner_text(), 'Lead Converted ID',
                ) != expected_business_id:
                    raise ConversionStopped('Redirected Contact Lead business ID mismatch')
            finally:
                page.get_by_role('button', name='Cancel', exact=True).last.click()
            return {'status': 'ALREADY_CONVERTED', 'lead_id': args.lead_id,
                    'contact_id': redirected_id, 'cms_contact_id': cms,
                    'cdms_status': 'SYNCED' if cms else 'UNVERIFIED'}

        page.get_by_text(args.email, exact=False).first.wait_for(timeout=20000)
        status = preflight_lead_text(
            page.locator('body').inner_text(),
            expected_email=args.email, korean_name=args.korean_name,
            convert_visible=page.get_by_role('button', name='Convert', exact=True).count() == 1,
        )
        if status == 'needs_contact_verification':
            known = getattr(args, 'known_contact_id', None)
            if not known or not re.fullmatch(r'003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?', known):
                raise ConversionStopped('Convert unavailable; supply a verified existing Contact ID for read-only validation')
            lead_body = page.locator('body').inner_text()
            page.goto(f'{HOST}/lightning/r/Contact/{known}/view', wait_until='domcontentloaded')
            edit = page.get_by_role('button', name='Edit', exact=True).first
            edit.wait_for(timeout=20000)
            edit.click()
            page.locator('input[name=firstName]').wait_for(timeout=20000)
            contact_body = page.locator('body').inner_text()
            try:
                cms = verify_prior_conversion(
                    lead_body=lead_body, contact_body=contact_body,
                    expected_email=args.email, account_name=args.account_name,
                    expected_korean_name=args.korean_name,
                )
            finally:
                page.get_by_role('button', name='Cancel', exact=True).last.click()
            return {'status': 'ALREADY_CONVERTED', 'lead_id': args.lead_id,
                    'contact_id': known, 'cms_contact_id': cms,
                    'cdms_status': 'SYNCED' if cms else 'UNVERIFIED'}

        # Form-only audit: no Contact, Account, Opportunity, or CDMS writes.
        # A missing Billing Address blocks --execute but must not block Cancel-only UI checks.
        if getattr(args, 'audit_convert_form', False):
            if args.org_type != 'Academic':
                raise ConversionStopped('Non-Academic form audit not validated')
            names = build_form_name_plan(
                korean_full_name=args.korean_name,
                romanized_surname=args.surname,
                romanized_given_syllables=args.given,
            )
            page.goto(f'{HOST}/lightning/r/Account/{args.account_id}/view',
                      wait_until='domcontentloaded')
            page.get_by_text(args.account_name, exact=True).first.wait_for(timeout=20000)
            page.goto(f'{HOST}/lightning/r/Lead/{args.lead_id}/view',
                      wait_until='domcontentloaded')
            page.get_by_text(args.email, exact=False).first.wait_for(timeout=20000)
            if preflight_lead_text(
                page.locator('body').inner_text(),
                expected_email=args.email,
                korean_name=args.korean_name,
                convert_visible=page.get_by_role('button', name='Convert', exact=True).count() == 1,
            ) != 'ready':
                raise ConversionStopped('Lead changed during Cancel-only form audit')
            modal = prepare_conversion_modal(page, names, args.account_name)
            try:
                result = {'status': 'FORM_AUDIT_PASS_CANCELLED',
                          'lead_id': args.lead_id,
                          'account_id': args.account_id,
                          'address_verified': 'NOT_CHECKED',
                          'write_performed': 'NO'}
            finally:
                modal.get_by_role('button', name='Cancel', exact=True).last.click()
            if modal.count():
                raise ConversionStopped('Convert form did not close after Cancel')
            return result

        # Only leads proven unconverted need an Account address lookup.
        # Recheck lead identity after navigating back from Account details.
        address = read_account_address(page, args.account_id, args.account_name)
        page.goto(f'{HOST}/lightning/r/Lead/{args.lead_id}/view', wait_until='domcontentloaded')
        page.get_by_text(args.email, exact=False).first.wait_for(timeout=20000)
        if preflight_lead_text(
            page.locator('body').inner_text(), expected_email=args.email,
            korean_name=args.korean_name,
            convert_visible=page.get_by_role('button', name='Convert', exact=True).count() == 1,
        ) != 'ready':
            raise ConversionStopped('Lead state changed after Account lookup; refusing conversion')

        # Non-academic Job Function menus require independent live mapping.
        if args.org_type != 'Academic':
            raise ConversionStopped('Non-Academic live Job Function mapping is not approved yet')
        plan = build_contact_plan(
            korean_full_name=args.korean_name, romanized_surname=args.surname,
            romanized_given_syllables=args.given, verified_account_id=args.account_id,
            account_address=address, org_type=args.org_type, job_options=[ACADEMIC_PI],
        )
        if not args.execute:
            return {'status': 'DRY_RUN_PASS', 'lead_id': args.lead_id,
                    'account_id': args.account_id, 'write_performed': 'NO'}

        # Side effect #1: Convert. Never repeat automatically after timeout.
        modal = prepare_conversion_modal(page, plan, args.account_name)
        modal.get_by_role('button', name='Convert', exact=True).click()
        page.get_by_text('Your lead has been converted', exact=True).wait_for(timeout=30000)
        links = [(a.inner_text().strip(), a.get_attribute('href') or '') for a in page.locator('a').all()]
        contact_id = contact_id_from_success_links(links)
        if args.account_name not in page.locator('body').inner_text():
            raise ConversionStopped('Converted Account differs from verified Account')

        # Side effect #2: Complete required Contact details before CDMS.
        page.goto(f'{HOST}/lightning/r/Contact/{contact_id}/view', wait_until='domcontentloaded')
        edit = page.get_by_role('button', name='Edit', exact=True).first
        edit.wait_for(timeout=20000)
        edit.click()
        page.locator('input[name=firstName]').wait_for(timeout=20000)
        page.locator('input[name=firstName]').fill(plan.first_name)
        page.locator('input[name=lastName]').fill(plan.last_name)
        page.get_by_role('combobox', name='Org Type Group').click()
        page.get_by_role('option', name='Academic', exact=True).click()
        page.get_by_role('combobox', name='Job Function').click()
        options = [o.inner_text().strip() for o in page.locator('[role=option]').all()]
        first = next((o for o in options if o.startswith('ACADEMIC:')), None)
        if first != plan.job_function:
            raise ConversionStopped('Live first Academic Job Function is not PI')
        page.get_by_role('option', name=plan.job_function, exact=True).click()
        page.locator('textarea[name=street]').fill(plan.shipping_street)
        for key, value in [('city', plan.shipping_city), ('province', plan.shipping_state),
                           ('postalCode', plan.shipping_postal_code), ('country', plan.shipping_country)]:
            page.locator('input[name=' + key + ']').fill(value)
        page.get_by_role('button', name='Save', exact=True).last.click()
        page.get_by_text('was saved.', exact=False).first.wait_for(timeout=30000)
        verify_contact_readback(page, contact_id, plan)

        # Side effect #3: CDMS Sync, only if no CMS Contact ID exists.
        cms = cms_id_from_view(page.locator('body').inner_text())
        if cms:
            return {'status': 'ALREADY_SYNCED', 'contact_id': contact_id, 'cms_contact_id': cms}
        require_one_visible(page.get_by_role('button', name='Sync To CDMS', exact=True),
                            'Sync To CDMS').click()
        page.get_by_text('Sync completed', exact=True).first.wait_for(timeout=45000)
        page.goto(f'{HOST}/lightning/r/Contact/{contact_id}/view', wait_until='domcontentloaded')
        page.get_by_text('CMS Contact ID', exact=True).first.wait_for(timeout=20000)
        page.wait_for_timeout(1400)
        cms = cms_id_from_view(page.locator('body').inner_text())
        if not cdms_sync_verified(sync_message='Sync completed', cms_contact_id=cms):
            raise ConversionStopped('Sync toast was shown but no persisted CMS ID')
        return {'status': 'CDMS_CONFIRMED', 'contact_id': contact_id, 'cms_contact_id': cms}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ['lead-id', 'account-id', 'account-name', 'email',
                'korean-name', 'surname']:
        ap.add_argument('--' + key, required=True)
    ap.add_argument('--given', action='append', required=True)
    ap.add_argument('--org-type', default='Academic')
    ap.add_argument('--known-contact-id', default=None,
                    help='Existing Contact ID used only to verify a Lead already converted')
    ap.add_argument('--lead-business-id', default=None,
                    help='Optional human-readable converted Lead ID for read-only cross-check')
    ap.add_argument('--cdp', default='http://127.0.0.1:9222')
    ap.add_argument('--audit-convert-form', action='store_true',
                    help='Open, populate, validate, and Cancel the unsaved Convert form')
    ap.add_argument('--execute', action='store_true',
                    help='Explicitly authorize live Salesforce conversion, editing, and CDMS sync')
    args = ap.parse_args()
    if args.execute and args.audit_convert_form:
        ap.error('--execute and --audit-convert-form are mutually exclusive')
    try:
        result = run(args)
    except ConversionStopped as err:
        print({'status': 'HOLD', 'reason': str(err)})
        return 2
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
