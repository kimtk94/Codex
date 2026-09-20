from pathlib import Path

from engine import news_ingest_v1
from engine.news_ingest_v1 import (
    Entity,
    HttpAccessDeniedError,
    HttpRateLimitError,
    Spool,
    clean_url,
    event_classify,
    http_get,
    parse_feed,
)


def test_url_tracking_removed():
    assert clean_url("https://example.com/a?utm_source=x&id=7") == "https://example.com/a?id=7"


def test_rss_timestamp_and_macro_classification():
    raw = b"""<?xml version="1.0"?><rss><channel><item>
    <title>Consumer Price Index update</title>
    <link>https://example.com/cpi</link><guid>cpi-1</guid>
    <pubDate>Fri, 18 Sep 2026 12:30:00 GMT</pubDate>
    </item></channel></rss>"""
    row = parse_feed(raw, "bls_cpi", (Entity("GLOBAL", "GLOBAL", 1.0, "test"),))[0]
    assert row.time_quality == "PUBLISHER_TS"
    assert event_classify(row.title, row.source, {})[0] == "MACRO"


def test_spool_is_idempotent(tmp_path: Path):
    raw = b"""<?xml version="1.0"?><rss><channel><item>
    <title>Federal Reserve rate update</title>
    <link>https://example.com/fed</link><guid>fed-1</guid>
    <pubDate>Fri, 18 Sep 2026 18:00:00 GMT</pubDate>
    </item></channel></rss>"""
    row = parse_feed(raw, "fed_monetary", (Entity("GLOBAL", "GLOBAL", 1.0, "test"),))[0]
    spool = Spool(tmp_path / "spool.sqlite3")
    assert spool.put(row) is True
    assert spool.put(row) is False
    assert spool.stats()["articles"] == 1
    assert len(spool.entities(row.article_id)) == 1



def test_macro_full_release_names_are_classified():
    assert event_classify("Consumer Price Index update", "bls_cpi", {})[0] == "MACRO"
    assert event_classify("Employment Situation release", "bls_employment", {})[0] == "MACRO"
    assert event_classify("Job Openings and Labor Turnover Survey", "bls_jolts", {})[0] == "MACRO"


def test_http_429_is_not_immediately_retried(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        status_code = 429
        headers = {"Retry-After": "30"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    monkeypatch.setattr(news_ingest_v1.httpx, "Client", FakeClient)

    try:
        http_get("https://example.com/rate-limited", retries=3)
        assert False, "expected HttpRateLimitError"
    except HttpRateLimitError as exc:
        assert exc.retry_after_seconds == 30

    assert calls["count"] == 1



def test_http_403_is_not_immediately_retried(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        status_code = 403
        headers = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    monkeypatch.setattr(news_ingest_v1.httpx, "Client", FakeClient)

    try:
        http_get("https://www.sec.gov/files/company_tickers.json", retries=3)
        assert False, "expected HttpAccessDeniedError"
    except HttpAccessDeniedError as exc:
        assert exc.status_code == 403

    assert calls["count"] == 1


def test_sec_company_map_uses_stale_cache_on_refresh_error(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    cache = state_dir / "sec_company_tickers.json"
    cache.write_text(
        '{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}',
        encoding="utf-8",
    )

    def denied(*args, **kwargs):
        raise HttpAccessDeniedError(
            "https://www.sec.gov/files/company_tickers.json", 403
        )

    monkeypatch.setattr(news_ingest_v1, "http_get", denied)
    mapping = news_ingest_v1.sec_company_map(
        state_dir, "Kalman Research admin@example.com", max_age_hours=0
    )

    assert mapping["AAPL"]["cik"] == "0000320193"
