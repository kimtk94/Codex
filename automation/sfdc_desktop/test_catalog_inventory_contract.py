import unittest

from catalog_inventory_contract import count_processes, validate_catalog


def good(service="Synthetic mRNA service", category="Synthetic RNA"):
    return {
        "category": category,
        "service": service,
        "state": "PASS",
        "save_clicked": False,
        "done_clicked": False,
        "fields": {
            "Sample Number": {"count": 1, "enabled": True, "value": "1"},
            "Data Size": {"count": 1, "enabled": False},
        },
        "details": "Process List\n1\nLibrary preparation\nmRNA library preparation\n2\nSequencing by sample\nSequencing\nCancelDone",
    }


class CatalogContractTests(unittest.TestCase):
    def test_parse_process_rows(self):
        self.assertEqual(count_processes(good()["details"]), 2)

    def test_accept_disabled_data_size(self):
        self.assertEqual(validate_catalog([good()])["verified_services"], 1)

    def test_minimum_coverage(self):
        with self.assertRaises(ValueError):
            validate_catalog([good()], minimum=2)

    def test_reject_duplicate_product(self):
        with self.assertRaises(ValueError):
            validate_catalog([good(), good()])

    def test_reject_save_or_done(self):
        for key in ("save_clicked", "done_clicked"):
            row = good()
            row[key] = True
            with self.assertRaises(ValueError):
                validate_catalog([row])

    def test_reject_false_success_without_process(self):
        row = good()
        row["details"] = "Sample Number, Data Size, Next"
        with self.assertRaises(ValueError):
            validate_catalog([row])

    def test_hold_counts_separately(self):
        held = good("Synthetic WGS")
        held["state"] = "HOLD_TimeoutError"
        self.assertEqual(validate_catalog([good(), held]), {
            "verified_services": 1, "held_services": 1, "unique_rows": 2
        })


if __name__ == "__main__":
    unittest.main()
