def normalize_status(value):
    """Return PASS/FAIL/HOLD according to the independent V2 goal."""
    if not isinstance(value, str):
        return 'HOLD'
    normalized = str(value).strip().lower()
    if normalized in ['pass', 'passed', 'ok', 'done', 'success']:
        return 'PASS'
    elif normalized in ['fail', 'failed', 'error']:
        return 'FAIL'
    else:
        return 'HOLD'