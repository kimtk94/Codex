"""Offline validation of the Salesforce UI worker. No Salesforce credentials/API."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import runner


class QueueContractTests(unittest.TestCase):
    def write_queue(self, directory, rows):
        p = Path(directory) / "queue.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["source_id", "object_type", "record_key", "Subject"])
            w.writeheader()
            w.writerows(rows)
        return p

    def test_queue_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.write_queue(td, [{"source_id": "css-1", "object_type": "Task",
                "record_key": "account-1:mail-1", "Subject": "Follow up"}])
            self.assertEqual(len(runner.load_queue(p)), 1)

    def test_queue_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.write_queue(td, [
                {"source_id": "css-1", "object_type": "Task", "record_key": "same"},
                {"source_id": "css-2", "object_type": "Task", "record_key": "same"}])
            with self.assertRaises(ValueError):
                runner.load_queue(p)

    def test_unknown_object_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.write_queue(td, [
                {"source_id": "css-1", "object_type": "User", "record_key": "one"}])
            with self.assertRaises(ValueError):
                runner.load_queue(p)

    def test_blank_queue_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.csv"
            p.write_text("source_id,object_type,record_key\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.load_queue(p)

    def test_block_external_sites(self):
        for url in ["https://salesforce.com.evil.example/path",
                    "https://example.org", "file:///etc/passwd"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                runner.check_url(url)

    def test_allow_salesforce_lightning(self):
        self.assertEqual(runner.check_url(
            "https://test.lightning.force.com/lightning/page/home"),
            "https://test.lightning.force.com/lightning/page/home")

    def test_unmapped_fields_are_not_submitted(self):
        page = MagicMock()
        locator = MagicMock()
        locator.count.return_value = 1
        locator.is_visible.return_value = True
        locator.is_enabled.return_value = True
        page.locator.return_value = locator
        row = {"source_id": "css-1", "object_type": "Task", "record_key": "k",
               "Subject": "Follow up", "Email": "not-mapped@example.invalid"}
        mapping = {"Task": {"url": "https://test.lightning.force.com/lightning/o/Task/new",
                            "fields": {"Subject": "[name=Subject]"}}}
        status = runner.fill_form(page, row, mapping)
        self.assertEqual(status["status"], "FORM_FILLED_NOT_SAVED")
        locator.fill.assert_called_once_with("Follow up")
        page.get_by_role.assert_not_called()
        page.locator.assert_called_once_with("[name=Subject]")

    def test_unsafe_mapped_field_rejected(self):
        page = MagicMock()
        row = {"source_id": "a", "object_type": "Task", "record_key": "k",
               "OwnerId": "005-test"}
        mapping = {"Task": {"url": "https://test.lightning.force.com",
                            "fields": {"OwnerId": "#owner"}}}
        with self.assertRaises(ValueError):
            runner.fill_form(page, row, mapping)


if __name__ == "__main__":
    unittest.main()
