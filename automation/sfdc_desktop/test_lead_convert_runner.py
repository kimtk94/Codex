"""Offline, side-effect-free runner safety checks (no Salesforce)."""
import unittest
from lead_convert_runner import (
    ConversionStopped,
    extract_billing_address,
    preflight_lead_text,
    contact_id_from_success_links,
    cms_id_from_view,
    verify_prior_conversion,
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
        self.assertEqual(preflight_lead_text('김철수\na@example.org\nConverted',
            expected_email='a@example.org', korean_name='김철수',
            convert_visible=False), 'needs_contact_verification')

    def test_missing_convert_requires_independent_proof(self):
        self.assertEqual(preflight_lead_text('김철수\na@example.org\nNew',
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
        self.assertEqual(preflight_lead_text('김철수\na@example.org\nNew',
            expected_email='a@example.org', korean_name='김철수',
            convert_visible=True), 'ready')

    def test_bad_email_or_name_fails_closed(self):
        with self.assertRaises(ConversionStopped):
            preflight_lead_text('김철수\nb@example.org',
                expected_email='a@example.org', korean_name='김철수', convert_visible=True)
        with self.assertRaises(ConversionStopped):
            preflight_lead_text('이영희\na@example.org',
                expected_email='a@example.org', korean_name='김철수', convert_visible=True)

    def test_contact_link_must_be_specific(self):
        self.assertEqual(contact_id_from_success_links(
            [('Sample', '/lightning/r/003000000000001AAA/view')]),
            '003000000000001AAA')
        with self.assertRaises(ConversionStopped):
            contact_id_from_success_links(
                [('Account', '/lightning/r/001000000000001AAA/view')])

    def test_cdms_id_persisted(self):
        self.assertEqual(cms_id_from_view(
            'CMS Contact ID\n\nCP12345678\nAccount Name'), 'CP12345678')
        self.assertEqual(cms_id_from_view('CMS Contact ID\n\nAccount Name'), '')


if __name__ == '__main__':
    unittest.main()
