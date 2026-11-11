import unittest
from unittest.mock import Mock, patch
from sfdc_record_catalog import (
    quote_price_breakdown_with_retry, retryable_modal_price_read_error
)

class QuoteLiveRetryTests(unittest.TestCase):
    def test_transient_timeout_retries_once_and_returns_verified_price(self):
        page=Mock()
        with patch("sfdc_record_catalog.quote_price_breakdown",
                   side_effect=[TimeoutError("transient"),{"pricingStatus":"VERIFIED_PROCESS_LINES","sourcePackVerified":True}]) as reader:
            result=quote_price_breakdown_with_retry(page,"a0P000000000000AAA",12,5,1955000)
        self.assertEqual(result["pricingStatus"],"VERIFIED_PROCESS_LINES")
        self.assertEqual(reader.call_count,2)
        page.wait_for_timeout.assert_called_once_with(800)
    def test_price_total_and_pack_mismatch_never_retried(self):
        for code in ("SOURCE_MODAL_QUOTE_NET_MISMATCH","SOURCE_SAME_SAMPLE_PACK_CONFLICT",
                     "SOURCE_MODAL_HEADERS_CHANGED","PROCESS_MODAL_PRICE_RANGE"):
            with self.subTest(code=code):
                page=Mock()
                with patch("sfdc_record_catalog.quote_price_breakdown",
                           side_effect=ValueError(code)) as reader:
                    with self.assertRaisesRegex(ValueError,code):
                        quote_price_breakdown_with_retry(page,"a0P000000000000AAA",12,5,1955000)
                reader.assert_called_once()
                page.wait_for_timeout.assert_not_called()
    def test_repeated_timeouts_hold(self):
        page=Mock()
        with patch("sfdc_record_catalog.quote_price_breakdown",
                   side_effect=TimeoutError("transient")) as reader:
            with self.assertRaises(TimeoutError):
                quote_price_breakdown_with_retry(page,"a0P000000000000AAA",12,5,1955000)
        self.assertEqual(reader.call_count,2)
    def test_only_narrow_load_errors_retry(self):
        self.assertTrue(retryable_modal_price_read_error(TimeoutError()))
        self.assertTrue(retryable_modal_price_read_error(ValueError("SOURCE_PROCESS_MATRIX_NOT_LOADED")))
        self.assertFalse(retryable_modal_price_read_error(ValueError("SOURCE_MODAL_QUOTE_NET_MISMATCH")))
if __name__=="__main__":unittest.main()
