"""Standalone, non-production example for an Ollama code-improvement goal."""


def normalize_status(value):
    """Enhanced implementation to handle various input cases."""
    if value is None or value == '' or isinstance(value, (int, float, dict)):
        return 'HOLD'
    normalized = str(value).strip().upper()
    if normalized in ['PASS', 'FAIL']:
        return normalized
    return 'HOLD'
