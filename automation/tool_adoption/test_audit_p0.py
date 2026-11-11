"""Unit tests for the read-only repository inventory."""
import tempfile
import unittest
from pathlib import Path

from audit_p0 import inventory


class AuditP0Tests(unittest.TestCase):
    def test_detects_path_and_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: tests\n")
            (root / "tools.py").write_text("import markitdown\n")
            result = inventory(root)
            self.assertTrue(result["signals"]["ci"]["detected"])
            self.assertTrue(result["signals"]["markitdown"]["detected"])
            self.assertFalse(result["signals"]["openclaw"]["detected"])

    def test_skips_symlink_and_large_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "large.txt").write_text("n8n" + "x" * 1048576)
            (root / "regular.txt").write_text("harness")
            result = inventory(root)
            self.assertEqual(result["large_files_skipped"], 1)
            self.assertFalse(result["signals"]["n8n"]["detected"])
            self.assertTrue(result["signals"]["harness"]["detected"])

    def test_ignores_self_references_and_generated_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tool_adoption").mkdir()
            (root / "tool_adoption" / "scan.py").write_text("superpowers openclaw")
            (root / "vercel_manifest.json").write_text("n8n ecc")
            result = inventory(root)
            self.assertFalse(result["signals"]["superpowers"]["detected"])
            self.assertFalse(result["signals"]["openclaw"]["detected"])
            self.assertFalse(result["signals"]["n8n"]["detected"])
            self.assertFalse(result["signals"]["ecc"]["detected"])

    def test_output_is_path_only_no_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.md").write_text("codex TOKEN=secret-do-not-print")
            result = inventory(root)
            self.assertNotIn("secret-do-not-print", str(result))
            self.assertEqual(result["signals"]["codex"]["evidence"][0]["path"], "config.md")


if __name__ == "__main__":
    unittest.main()
