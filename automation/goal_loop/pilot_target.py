def normalize_status(value):
    if value is None or value == '' or isinstance(value, (int, float, dict)):
        return 'HOLD'
    normalized = str(value).strip().upper()
    if normalized in ['PASS', 'FAIL']:
        return normalized
    if normalized in ['OK', 'DONE', 'SUCCESS']:
        return 'PASS'
    if normalized in ['UNKNOWN', 'ERROR']:
        return 'FAIL'
    return 'HOLD'