"""V2 nonproduction status normalizer; intentionally incomplete baseline."""


def normalize_status(value):
    """Return PASS/FAIL/HOLD according to the independent V2 goal."""
    return str(value).strip().upper()
