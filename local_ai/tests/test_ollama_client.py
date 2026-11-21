"""Offline unit tests. No real Ollama daemon/model/internet required."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from local_ai import ollama_client as client


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.data


class OllamaTests(unittest.TestCase):
    def test_local_model_filter(self):
        self.assertTrue(client.model_is_local("qwen3:4b"))
        self.assertFalse(client.model_is_local("qwen3:4b:cloud"))
        self.assertFalse(client.model_is_local("model:cloud"))
        self.assertFalse(client.model_is_local("model;curl evil"))

    @patch.object(client, "urlopen")
    def test_tags_are_localhost_only(self, http):
        http.return_value = FakeResponse({"models": [{"name": "qwen3:4b"}]})
        self.assertEqual(client.available_models(), ["qwen3:4b"])
        request = http.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/tags")

    @patch.object(client, "urlopen")
    def test_analyze_is_read_only_json(self, http):
        http.return_value = FakeResponse({
            "response": json.dumps({
                "summary": "요약", "evidence": [], "actions": [], "uncertainties": []
            }, ensure_ascii=False)
        })
        result = client.analyze("Synthetic test: customer requested a quotation.", "lead_triage")
        self.assertEqual(result["summary"], "요약")
        request = http.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertIn("contact", payload["system"])

    def test_bad_input_is_rejected_without_http(self):
        with self.assertRaises(ValueError):
            client.analyze("   ")
        with self.assertRaises(ValueError):
            client.analyze("x" * (client.MAX_INPUT_CHARS + 1))
        with self.assertRaises(ValueError):
            client.analyze("test", model="qwen3:4b:cloud")
        with self.assertRaises(ValueError):
            client.analyze("test", task="dangerous")

    @patch.object(client, "analyze")
    def test_cli_saves_to_explicit_local_path(self, analyze):
        analyze.return_value = {"summary": "ok", "evidence": [], "actions": [], "uncertainties": []}
        with TemporaryDirectory() as folder:
            inp = Path(folder) / "source.txt"
            out = Path(folder) / "results" / "output.json"
            inp.write_text("Synthetic data only", encoding="utf-8")
            rc = client.cli(["--input", str(inp), "--output", str(out)])
            self.assertEqual(rc, 0)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(doc["review_required"])
            self.assertEqual(doc["result"]["summary"], "ok")
            self.assertNotIn("Synthetic data only", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
