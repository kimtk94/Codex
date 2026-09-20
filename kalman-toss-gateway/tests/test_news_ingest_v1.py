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



def test_sec_runtime_gate_disables_collection(tmp_path, monkeypatch):
    spool = Spool(tmp_path / "spool.sqlite3")
    monkeypatch.setenv("KALMAN_NEWS_SEC_ENABLED", "false")
    monkeypatch.setenv("KALMAN_NEWS_SEC_USER_AGENT", "KalmanResearch/1.0 test@example.com")

    def should_not_run(*args, **kwargs):
        raise AssertionError("SEC network access should be skipped when disabled")

    monkeypatch.setattr(news_ingest_v1, "sec_company_map", should_not_run)

    seen, inserted = news_ingest_v1.collect_sec(
        spool,
        {"enabled": True, "min_interval_seconds": 0},
        {"US": ["AAPL"], "KR": [], "CRYPTO": []},
        tmp_path / "state",
    )

    assert seen == 0
    assert inserted == 0



def test_collect_all_never_prefetches_sec_when_runtime_gate_off(tmp_path, monkeypatch):
    spool = Spool(tmp_path / "spool.sqlite3")
    monkeypatch.setenv("KALMAN_NEWS_SEC_ENABLED", "false")
    monkeypatch.setenv("KALMAN_NEWS_SEC_USER_AGENT", "KalmanResearch/1.0 test@example.com")

    monkeypatch.setattr(
        news_ingest_v1,
        "latest_universe",
        lambda *args, **kwargs: {"US": ["AAPL"], "KR": [], "CRYPTO": ["BTC", "ETH"]},
    )

    def sec_network_must_not_run(*args, **kwargs):
        raise AssertionError("SEC alias refresh should not run while disabled")

    monkeypatch.setattr(news_ingest_v1, "sec_company_map", sec_network_must_not_run)
    monkeypatch.setattr(news_ingest_v1, "collect_rss", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(news_ingest_v1, "collect_sec", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(news_ingest_v1, "collect_dart", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(news_ingest_v1, "collect_gdelt", lambda *args, **kwargs: (0, 0))

    result = news_ingest_v1.collect_all(
        spool,
        {
            "rss_sources": [],
            "sec": {"enabled": True, "min_interval_seconds": 0},
            "dart": {"enabled": False},
            "gdelt": {"enabled": True, "min_interval_seconds": 0},
        },
        None,
        tmp_path / "state",
    )

    assert result["seen"] == 0
    assert result["inserted"] == 0


def test_dart_runtime_gate_disables_collection(tmp_path, monkeypatch):
    spool = Spool(tmp_path / "spool.sqlite3")
    monkeypatch.setenv("KALMAN_NEWS_DART_ENABLED", "false")
    monkeypatch.setenv("DART_API_KEY", "dummy")

    def should_not_run(*args, **kwargs):
        raise AssertionError("OpenDART network access should be skipped when disabled")

    monkeypatch.setattr(news_ingest_v1, "http_get", should_not_run)

    seen, inserted = news_ingest_v1.collect_dart(
        spool,
        {"enabled": True, "min_interval_seconds": 0},
        {"US": [], "KR": ["005930"], "CRYPTO": []},
    )

    assert seen == 0
    assert inserted == 0


def test_collect_all_never_prefetches_dart_when_runtime_gate_off(tmp_path, monkeypatch):
    spool = Spool(tmp_path / "spool.sqlite3")
    monkeypatch.setenv("KALMAN_NEWS_SEC_ENABLED", "false")
    monkeypatch.setenv("KALMAN_NEWS_DART_ENABLED", "false")
    monkeypatch.setenv("DART_API_KEY", "dummy")

    monkeypatch.setattr(
        news_ingest_v1,
        "latest_universe",
        lambda *args, **kwargs: {"US": [], "KR": ["005930"], "CRYPTO": ["BTC", "ETH"]},
    )

    def dart_network_must_not_run(*args, **kwargs):
        raise AssertionError("DART alias refresh should not run while disabled")

    monkeypatch.setattr(news_ingest_v1, "dart_company_map", dart_network_must_not_run)
    monkeypatch.setattr(news_ingest_v1, "collect_rss", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(news_ingest_v1, "collect_sec", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(news_ingest_v1, "collect_dart", lambda *args, **kwargs: (0, 0))
    monkeypatch.setattr(news_ingest_v1, "collect_gdelt", lambda *args, **kwargs: (0, 0))

    result = news_ingest_v1.collect_all(
        spool,
        {
            "rss_sources": [],
            "sec": {"enabled": False},
            "dart": {"enabled": True, "min_interval_seconds": 0},
            "gdelt": {"enabled": True, "min_interval_seconds": 0},
        },
        None,
        tmp_path / "state",
    )

    assert result["seen"] == 0
    assert result["inserted"] == 0


def test_disabled_source_clears_stale_error(tmp_path):
    spool = Spool(tmp_path / "spool.sqlite3")
    spool.record_source("sec_edgar", success=False, error="HTTP 403")
    before = spool.source_state("sec_edgar")
    assert before["last_error"] == "HTTP 403"

    spool.record_disabled("sec_edgar", "runtime_gate")
    after = spool.source_state("sec_edgar")
    assert after["last_error"] is None
    assert after["last_error_at"] is None
    assert '"status": "DISABLED"' in after["payload_json"]
    assert '"reason": "runtime_gate"' in after["payload_json"]


def test_sync_neon_updates_source_state_with_no_pending_articles(tmp_path, monkeypatch):
    spool = Spool(tmp_path / "spool.sqlite3")
    spool.record_source("fed_monetary", success=True, seen=1, inserted=1)
    monkeypatch.setenv("KALMAN_NEWS_NEON_SYNC_ENABLED", "true")

    calls = []

    class Tx:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    class Conn:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def transaction(self):
            return Tx()
        def execute(self, sql, params=None):
            calls.append((sql, params))
            return None

    monkeypatch.setattr(news_ingest_v1.psycopg, "connect", lambda *args, **kwargs: Conn())

    synced = news_ingest_v1.sync_neon(spool, "postgresql://example")
    assert synced == 0
    assert any("news_source_state" in sql for sql, _ in calls)
