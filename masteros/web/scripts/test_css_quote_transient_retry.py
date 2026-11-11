import unittest
from unittest.mock import Mock, patch
from sfdc_record_catalog import (
    quote_price_breakdown, quote_price_breakdown_with_retry, retryable_modal_price_read_error
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
    def test_disabled_source_add_edit_never_clicked_or_retried(self):
        page=Mock()
        tab=Mock(); edit=Mock()
        def control(role,**kwargs):
            if role=="tab":return tab
            if role=="button":return edit
            raise AssertionError("UNKNOWN_ROLE")
        page.get_by_role.side_effect=control
        edit.count.return_value=1
        edit.is_enabled.return_value=False
        with self.assertRaisesRegex(ValueError,"SOURCE_ADD_EDIT_DISABLED"):
            quote_price_breakdown(page,"a0P000000000000AAA",8,6,100000)
        tab.wait_for.assert_called_once_with(state="visible",timeout=13000)
        edit.first.wait_for.assert_called_once_with(state="visible",timeout=14000)
        edit.click.assert_not_called()
        self.assertEqual(page.goto.call_count,2)  # navigate back; discard
        self.assertEqual(page.wait_for_timeout.call_count,10)
        with patch("sfdc_record_catalog.quote_price_breakdown",
                   side_effect=ValueError("SOURCE_ADD_EDIT_DISABLED")) as reader:
            with self.assertRaisesRegex(ValueError,"SOURCE_ADD_EDIT_DISABLED"):
                quote_price_breakdown_with_retry(page,"a0P000000000000AAA",8,6,100000)
            reader.assert_called_once()
        self.assertFalse(retryable_modal_price_read_error(ValueError("SOURCE_ADD_EDIT_DISABLED")))

    def test_enabled_source_button_still_requires_real_modal(self):
        page=Mock()
        tab=Mock(); edit=Mock(); dialog=Mock()
        page.get_by_role.side_effect=lambda role,**kwargs: (
            tab if role=="tab" else edit if role=="button" else dialog)
        edit.count.return_value=1
        edit.is_enabled.return_value=True
        dialog.last.locator.return_value.filter.return_value.first.wait_for.side_effect=ValueError("SOURCE_PROCESS_MATRIX_NOT_LOADED")
        with self.assertRaisesRegex(ValueError,"SOURCE_PROCESS_MATRIX_NOT_UNIQUE"):
            quote_price_breakdown(page,"a0P000000000000AAA",8,6,100000)
        self.assertEqual(edit.click.call_count,2)
        edit.click.assert_any_call(trial=True,timeout=6500)
        edit.click.assert_any_call(timeout=9500)
        self.assertEqual(page.goto.call_count,2)

    def test_unactionable_add_edit_holds_without_real_click(self):
        page=Mock();tab=Mock();edit=Mock()
        page.get_by_role.side_effect=lambda role,**kwargs: (
            tab if role=="tab" else edit)
        edit.count.return_value=1
        edit.is_enabled.return_value=True
        edit.click.side_effect=TimeoutError("blocked_by_ui")
        with self.assertRaisesRegex(ValueError,"SOURCE_ADD_EDIT_NOT_INTERACTABLE"):
            quote_price_breakdown(page,"a0P000000000000AAA",8,6,100000)
        edit.click.assert_called_once_with(trial=True,timeout=6500)
        self.assertEqual(page.goto.call_count,2)
        self.assertFalse(retryable_modal_price_read_error(
            ValueError("SOURCE_ADD_EDIT_NOT_INTERACTABLE")))

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
