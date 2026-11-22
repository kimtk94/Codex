"""Local Ollama comparison probe; never runs model-generated Python.

Fixed, non-sensitive prompt. Run only by explicit user invocation on the
16GB laptop. GitHub Actions cannot access that machine's local Ollama.
"""
import argparse
import json
import time
import urllib.request

from automation.goal_loop.controller import Hold, require_local_model


MODEL_CHOICES = ("qwen25coder3b-16k", "qwen2.5-coder:7b")
CASES = {
    "pass": "PASS", "PASSED": "PASS", "ok": "PASS",
    "success": "PASS", "done": "PASS", "fail": "FAIL",
    "failed": "FAIL", "error": "FAIL", "unknown": "HOLD",
    "": "HOLD", "pending": "HOLD",
}


def summarize_probe(model, response, wall_seconds):
    """Score a structured answer *as data*, never as executable code."""
    if not isinstance(response, dict):
        raise ValueError("Invalid Ollama response")
    message = response.get("message") or {}
    content = message.get("content", "") if isinstance(message, dict) else ""
    try:
        mappings = json.loads(content)
        if not isinstance(mappings, dict):
            mappings = {}
    except (ValueError, TypeError):
        mappings = {}
    passed = sum(1 for key, value in CASES.items() if mappings.get(key) == value)
    eval_ns = response.get("eval_duration") or 0
    eval_tokens = response.get("eval_count") or 0
    throughput = round(eval_tokens / (eval_ns / 1e9), 2) if (
        isinstance(eval_ns, (int, float)) and eval_ns > 0 and
        isinstance(eval_tokens, (int, float)) and eval_tokens >= 0
    ) else None
    return {
        "model": model,
        "status": "COMPLETED",
        "quality_correct": passed,
        "quality_total": len(CASES),
        "quality_fraction": round(passed / len(CASES), 3),
        "wall_seconds": round(wall_seconds, 2),
        "generation_tokens_per_second": throughput,
        "load_seconds": round((response.get("load_duration") or 0) / 1e9, 2),
        "prompt_eval_seconds": round((response.get("prompt_eval_duration") or 0) / 1e9, 2),
        "actual_v2_CI_pass": "NOT_TESTED_BY_PROBE",
    }


def probe(model, timeout=180):
    """One bounded, cold-load task on loopback; no auto install or code execution."""
    if model not in MODEL_CHOICES:
        raise ValueError("Model not allowlisted")
    if not 10 <= timeout <= 600:
        raise ValueError("Timeout must be 10-600 seconds")
    require_local_model(model)
    prompt = (
        "Return a JSON object with precisely these string keys: "
        + json.dumps(list(CASES), ensure_ascii=False)
        + ". Values must be PASS for pass/passed/ok/done/success, FAIL for "
        "fail/failed/error and HOLD for unknown/pending/empty string. "
        "Ignore letter case in the key when classifying, but preserve each key "
        "exactly. No prose or Markdown."
    )
    payload = {
        "model": model, "stream": False, "format": "json", "keep_alive": "0",
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_ctx": 2048, "num_predict": 160},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        answer = json.load(response)
    return summarize_probe(model, answer, time.monotonic() - started)


def main():
    parser = argparse.ArgumentParser(description="Read-only local 3B/7B response probe")
    parser.add_argument("--model", choices=MODEL_CHOICES, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        report = probe(args.model, args.timeout)
    except (Hold, TimeoutError, OSError, ValueError, KeyError) as exc:
        report = {
            "model": args.model, "status": "HOLD",
            "reason": type(exc).__name__, "actual_v2_CI_pass": "NOT_TESTED_BY_PROBE",
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
