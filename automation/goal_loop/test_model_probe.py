"""Unit tests for local comparison probe; never contact Ollama or run model code."""
import io
import json
import unittest
from unittest.mock import patch

from automation.goal_loop.model_probe import (
    CASES, probe, summarize_probe,
)


class ModelProbeTests(unittest.TestCase):
    def test_correct_structured_response_is_data_only(self):
        response = {
            "message": {"content": json.dumps(CASES)},
            "eval_count": 40, "eval_duration": 2_000_000_000,
            "load_duration": 1_000_000_000,
            "prompt_eval_duration": 500_000_000,
        }
        result = summarize_probe("qwen25coder3b-16k", response, 4.5)
        self.assertEqual(result["quality_correct"], len(CASES))
        self.assertEqual(result["quality_fraction"], 1.0)
        self.assertEqual(result["generation_tokens_per_second"], 20.0)
        self.assertEqual(result["actual_v2_CI_pass"], "NOT_TESTED_BY_PROBE")

    def test_hostile_output_is_never_run(self):
        response = {"message": {"content": "__import__('os').system('echo danger')"}}
        result = summarize_probe("qwen2.5-coder:7b", response, 1.0)
        self.assertEqual(result["quality_correct"], 0)
        self.assertIsNone(result["generation_tokens_per_second"])

    def test_local_request_is_bounded_and_credential_free(self):
        response = {
            "message": {"content": json.dumps(CASES)},
            "eval_count": 8, "eval_duration": 1_000_000_000,
        }
        with patch("automation.goal_loop.model_probe.require_local_model") as installed, \
             patch("automation.goal_loop.model_probe.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(response).encode("utf-8"))) as request, \
             patch("automation.goal_loop.model_probe.time.monotonic",
                   side_effect=[10, 11]):
            result = probe("qwen2.5-coder:7b", timeout=120)
        installed.assert_called_once_with("qwen2.5-coder:7b")
        args, kwargs = request.call_args
        self.assertEqual(kwargs["timeout"], 120)
        self.assertIn("127.0.0.1:11434", args[0].full_url)
        payload = json.loads(args[0].data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen2.5-coder:7b")
        self.assertEqual(payload["keep_alive"], "0")
        self.assertNotIn("tools", payload)
        self.assertEqual(result["wall_seconds"], 1.0)

    def test_nonallowlisted_model_is_rejected_before_request(self):
        with patch("automation.goal_loop.model_probe.urllib.request.urlopen") as request:
            with self.assertRaises(ValueError):
                probe("untrusted-model")
        request.assert_not_called()

    def test_unbounded_timeout_is_not_allowed(self):
        with self.assertRaises(ValueError):
            probe("qwen2.5-coder:7b", timeout=10000)


if __name__ == "__main__":
    unittest.main()
