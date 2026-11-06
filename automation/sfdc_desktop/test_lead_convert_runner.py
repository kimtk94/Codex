"""Offline, side-effect-free runner safety checks (no Salesforce)."""
import unittest
from lead_convert_runner import (
    ConversionStopped,
    extract_billing_address,
    preflight_lead_text,
    contact_id_from_success_links,
    cms_id_from_view,
    verify_prior_conversion,
    contact_id_from_url,
    require_redirected_contact_identity,
)


class RunnerSafetyTests(unittest.TestCase):
    def test_extract_account_billing_address(self):
        text = ('Account\nAddress Information\nBilling Address\n'
                '100, Example-ro, Sample-gu\nIncheon, 22212\nKorea\n'
                'Edit Billing Address\nSystem Information')
        result = extract_billing_address(text)
        self.assertEqual(result['street'], '100, Example-ro, Sample-gu')
        self.assertEqual(result['city'], 'Incheon')
        self.assertEqual(result['postal_code'], '22212')
        self.assertEqual(result['country'], 'Korea')
        self.assertEqual(result['state'], '')

    def test_address_missing_cannot_write(self):
        with self.assertRaises(ConversionStopped):
            extract_billing_address('Billing Address\nKorea\nEdit Billing Address')

    def test_already_converted_is_terminal(self):
        self.assertEqual(preflight_lead_text('Lead\n김철수\na@example.org\nConverted',
            expected_email='a@example.org', korean_name='김철수',
            convert_visible=False), 'needs_contact_verification')

    def test_salesforce_reversed_korean_name_is_accepted(self):
        lead = ('Lead\n재욱 심\nEmail\ns@example.org\n'
                'Contact Information\nName\n재욱 심\nEdit Name\n')
        self.assertEqual(preflight_lead_text(
            lead, expected_email='s@example.org', korean_name='심재욱',
            convert_visible=True), 'ready')

    def test_header_only_lead_preflight_handles_loading_details(self):
        text = 'Lead\n재욱 심\nConvert\nEmail\ns@example.org\nTabs\nDetails\n'
        self.assertEqual(preflight_lead_text(
            text, expected_email='s@example.org',
            korean_name='심재욱', convert_visible=True), 'ready')

    def test_reversed_name_must_match_full_given_name(self):
        lead = ('Lead\n재욱 박\nEmail\ns@example.org\n'
                'Contact Information\nName\n재욱 박\nEdit Name\n')
        with self.assertRaisesRegex(ConversionStopped, 'Korean Lead name'):
            preflight_lead_text(
                lead, expected_email='s@example.org',
                korean_name='심재욱', convert_visible=True)

    def test_missing_convert_requires_independent_proof(self):
        self.assertEqual(preflight_lead_text('Lead\n김철수\na@example.org\nNew',
            expected_email='a@example.org', korean_name='김철수',
            convert_visible=False), 'needs_contact_verification')

    def test_prior_conversion_link_is_verified(self):
        lead = ('김철수\na@example.org\nSFDC Lead ID\n'
                'Lead-2026-11-05-11111\n')
        contact = ('김철수 ExampleName\nAccount Name\nExample University\n'
                   'Email\na@example.org\nLead Converted ID\n'
                   'Lead-2026-11-05-11111\nCMS Contact ID\nCP123456789\n')
        self.assertEqual(verify_prior_conversion(
            lead_body=lead, contact_body=contact, expected_email='a@example.org',
            account_name='Example University', expected_korean_name='김철수'),
            'CP123456789')

    def test_prior_conversion_rejects_wrong_lead(self):
        lead = '김철수\na@example.org\nSFDC Lead ID\nLead-2026-11-05-11111\n'
        contact = ('김철수\nExample University\na@example.org\n'
                   'Lead Converted ID\nLead-2026-11-05-22222\n')
        with self.assertRaisesRegex(ConversionStopped, 'not proven linked'):
            verify_prior_conversion(lead_body=lead, contact_body=contact,
                expected_email='a@example.org',
                account_name='Example University', expected_korean_name='김철수')

    def test_prior_conversion_rejects_wrong_email(self):
        lead = '김철수\na@example.org\nSFDC Lead ID\nLead-2026-11-05-11111\n'
        contact = ('김철수\nExample University\nwrong@example.org\n'
                   'Lead Converted ID\nLead-2026-11-05-11111\n')
        with self.assertRaisesRegex(ConversionStopped, 'email mismatch'):
            verify_prior_conversion(lead_body=lead, contact_body=contact,
                expected_email='a@example.org',
                account_name='Example University', expected_korean_name='김철수')

    def test_ready_lead_preflight_does_not_write(self):
        self.assertEqual(preflight_lead_text('Lead\n김철수\na@example.org\nNew',
            expected_email='a@example.org', korean_name='김철수',
            convert_visible=True), 'ready')

    def test_bad_email_or_name_fails_closed(self):
        with self.assertRaises(ConversionStopped):
            preflight_lead_text('Lead\n김철수\nb@example.org',
                expected_email='a@example.org', korean_name='김철수', convert_visible=True)
        with self.assertRaises(ConversionStopped):
            preflight_lead_text('Lead\n이영희\na@example.org',
                expected_email='a@example.org', korean_name='김철수', convert_visible=True)

    def test_contact_link_must_be_specific(self):
        self.assertEqual(contact_id_from_success_links(
            [('Sample', '/lightning/r/003000000000001AAA/view')]),
            '003000000000001AAA')
        with self.assertRaises(ConversionStopped):
            contact_id_from_success_links(
                [('Account', '/lightning/r/001000000000001AAA/view')])

    def test_converted_lead_redirect_url_parsing(self):
        self.assertEqual(contact_id_from_url(
            'https://novogene.lightning.force.com/lightning/r/Contact/003000000000001AAA/view'
        ), '003000000000001AAA')
        self.assertEqual(contact_id_from_url(
            'https://novogene.lightning.force.com/lightning/r/Lead/00Q000000000001AAA/view'
        ), '')

    def test_redirected_contact_id_email_and_names(self):
        details = dict(
            contact_id='003000000000001AAA',
            expected_contact_id='003000000000001AAA',
            email='a@example.org', expected_email='a@example.org',
            korean_name='김철수', expected_korean_name='김철수',
            english_name='KimCheolSu', expected_english_name='KimCheolSu',
        )
        require_redirected_contact_identity(**details)
        for override in (
            {'expected_contact_id': '003000000000002AAA'},
            {'expected_email': 'b@example.org'},
            {'expected_korean_name': '김영희'},
            {'expected_english_name': 'KimYoungHee'},
        ):
            with self.assertRaises(ConversionStopped):
                require_redirected_contact_identity(**dict(details, **override))

    def test_cdms_id_persisted(self):
        self.assertEqual(cms_id_from_view(
            'CMS Contact ID\n\nCP12345678\nAccount Name'), 'CP12345678')
        self.assertEqual(cms_id_from_view('CMS Contact ID\n\nAccount Name'), '')


if __name__ == '__main__':
    unittest.main()
