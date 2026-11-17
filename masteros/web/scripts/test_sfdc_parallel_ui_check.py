import unittest
from sfdc_parallel_ui_check import validate

class ParallelQuoteUiReadOnlyTest(unittest.TestCase):
    def test_valid_one_to_three_unique_native_quote_ids(self):
        ids=["a0P"+"A"*12,"a0P"+"B"*12,"a0P"+"C"*12]
        for n in range(1,4):
            self.assertEqual(validate({"mode":"QUOTE_UI_BATCH","recordIds":ids[:n]}),ids[:n])

    def test_invalid_batch_cannot_open_cross_origin_or_duplicate_tabs(self):
        good="a0P"+"A"*12
        bad=[
            {"mode":"QUOTE_UI_BATCH","recordIds":[]},
            {"mode":"QUOTE_UI_BATCH","recordIds":[good]*2},
            {"mode":"QUOTE_UI_BATCH","recordIds":[good]*4},
            {"mode":"QUOTE_UI_BATCH","recordIds":["https://example.com/"]},
            {"mode":"QUOTE_UI_BATCH","recordIds":["006"+"A"*12]},
            {"mode":"QUOTE_UI_BATCH","recordIds":["a0P"+"-"*12]},
            {"mode":"QUOTE_UI_BATCH","recordIds":"not_a_list"},
            {"mode":"SAVE","recordIds":[good]},
        ]
        for x in bad:
            with self.subTest(input=x),self.assertRaises(ValueError):
                validate(x)

if __name__=="__main__":
    unittest.main()
