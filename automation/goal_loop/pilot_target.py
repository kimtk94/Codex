def normalize_status(value):
    if value is None or value == '' or isinstance(value, (int, float, dict)):
        return 'HOLD'
    normalized = str(value).strip().upper()
    if normalized in ['PASS', 'FAIL']:
        return normalized
    return 'UNKNOWN'