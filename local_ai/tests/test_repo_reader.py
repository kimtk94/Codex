import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess

from local_ai import repo_reader


class RepoReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = Path(self.folder.name)
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        (self.root / "test.txt").write_text("LOCAL_CODEX_TEST_20261121\n", encoding="utf-8")
        (self.root / "example.py").write_text("print('hello')\n", encoding="utf-8")
        (self.root / ".env").write_text("API_KEY=SECRET\n", encoding="utf-8")
        (self.root / ".local_ai_data").mkdir()
        (self.root / ".local_ai_data" / "data.txt").write_text("PRIVATE\n")

    def tearDown(self):
        self.folder.cleanup()

    def test_actual_read_matches_file(self):
        root = repo_reader.repo_root(self.root)
        text, truncated = repo_reader.read_file(root, "test.txt")
        self.assertEqual(text, "LOCAL_CODEX_TEST_20261121\n")
        self.assertFalse(truncated)

    def test_list_includes_untracked_but_excludes_secrets(self):
        names = repo_reader.filenames(self.root)
        self.assertIn("test.txt", names)
        self.assertIn("example.py", names)
        self.assertNotIn(".env", names)
        self.assertNotIn(".local_ai_data/data.txt", names)

    def test_forbid_secret_and_traversal(self):
        for file in (".env", "../outside.txt", ".local_ai_data/data.txt", "secret_key.txt"):
            with self.assertRaises(ValueError):
                repo_reader.read_file(self.root, file)

    def test_cli_read_without_model_or_filesystem_write(self):
        with patch.object(repo_reader, "repo_root", return_value=self.root):
            status = repo_reader.main(["--repo", str(self.root), "--file", "test.txt"])
        self.assertEqual(status, 0)
        self.assertFalse((self.root / "results.json").exists())

    def test_oversized_file_is_labeled_truncated(self):
        (self.root / "large.txt").write_text("a" * (repo_reader.MAX_READ_BYTES + 5), encoding="utf-8")
        text, truncated = repo_reader.read_file(self.root, "large.txt")
        self.assertTrue(truncated)
        self.assertEqual(len(text), repo_reader.MAX_READ_BYTES)


if __name__ == "__main__":
    unittest.main()
