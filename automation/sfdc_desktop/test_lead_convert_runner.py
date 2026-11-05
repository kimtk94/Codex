"""Offline, side-effect-free runner safety checks (no Salesforce)."""
import unittest
from lead_convert_runner import (
    ConversionStopped,
    extract_billing_address,
    preflight_lead_text,
    contact_id_from_success_links,
    cms_id_from_view,
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
            convert_visible=False), 'already_converted')

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
