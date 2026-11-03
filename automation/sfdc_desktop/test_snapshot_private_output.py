"""Safety regression tests for sensitive Salesforce snapshot output paths."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capture_existing_opportunity_snapshot import require_private_output


class PrivateSnapshotOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / ".sfdc_desktop"
        self.private.mkdir()
        self.patch = patch(
            "capture_existing_opportunity_snapshot.Path.home",
            return_value=self.root
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_new_private_path_allowed(self):
        p = self.private / "baseline_test_PRIVATE.json"
        self.assertEqual(require_private_output(p), p)

    def test_existing_snapshot_never_overwritten(self):
        p = self.private / "baseline_test_PRIVATE.json"
        p.write_text("sensitive", encoding="utf-8")
        with self.assertRaises(ValueError):
            require_private_output(p)
        self.assertEqual(p.read_text(encoding="utf-8"), "sensitive")

    def test_repo_or_arbitrary_directory_blocked(self):
        outside = self.root / "Codex"
        outside.mkdir()
        with self.assertRaises(ValueError):
            require_private_output(outside / "customer_PRIVATE.json")

    def test_relative_path_blocked(self):
        with self.assertRaises(ValueError):
            require_private_output("baseline_test_PRIVATE.json")

    def test_traversal_outside_private_blocked(self):
        with self.assertRaises(ValueError):
            require_private_output(self.private / ".." / "customer_PRIVATE.json")

    def test_non_private_filename_rejected(self):
        with self.assertRaises(ValueError):
            require_private_output(self.private / "customer_data.json")

    def test_dotfile_rejected(self):
        with self.assertRaises(ValueError):
            require_private_output(self.private / ".secret_PRIVATE.json")

    def test_missing_private_directory_rejected(self):
        self.private.rmdir()
        with self.assertRaises(ValueError):
            require_private_output(self.private / "baseline_test_PRIVATE.json")

    def test_symlinked_output_name_rejected(self):
        p = self.private / "baseline_test_PRIVATE.json"
        other = self.root / "some_file.json"
        other.write_text("prior content", encoding="utf-8")
        try:
            p.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this Windows device")
        with self.assertRaises(ValueError):
            require_private_output(p)

    def test_symlinked_private_directory_rejected(self):
        self.private.rmdir()
        other = self.root / "fake_private"
        other.mkdir()
        try:
            self.private.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks unavailable on this Windows device")
        with self.assertRaises(ValueError):
            require_private_output(self.private / "customer_PRIVATE.json")


if __name__ == "__main__":
    unittest.main()
