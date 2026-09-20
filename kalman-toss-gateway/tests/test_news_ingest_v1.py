from pathlib import Path

from engine.news_ingest_v1 import (
    Entity,
    Spool,
    clean_url,
    event_classify,
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
