"""Hand-authored CI fixture. Not produced by a local Ollama model."""


def normalize_status(value):
    if not isinstance(value, str):
        return "HOLD"
    normalized = value.strip().casefold()
    if normalized in {"pass", "passed", "ok", "done", "success"}:
        return "PASS"
    if normalized in {"fail", "failed", "error"}:
        return "FAIL"
    return "HOLD"
