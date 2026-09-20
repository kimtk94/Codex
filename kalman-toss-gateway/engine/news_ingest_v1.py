from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import statistics
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import httpx
import psycopg
from dotenv import load_dotenv

UTC = timezone.utc
MARKETS = {"US", "KR", "CRYPTO", "GLOBAL"}


class HttpRateLimitError(RuntimeError):
    def __init__(self, url: str, retry_after_seconds: float | None = None):
        self.url = url
        self.retry_after_seconds = retry_after_seconds
        suffix = (
            f" retry_after={retry_after_seconds:.0f}s"
            if retry_after_seconds is not None else ""
        )
        super().__init__(f"HTTP 429 Too Many Requests: {url}{suffix}")


class HttpAccessDeniedError(RuntimeError):
    def __init__(self, url: str, status_code: int):
        self.url = url
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} access denied: {url}")


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid",
}
EVENT_RULES: list[tuple[str, tuple[str, ...], float]] = [
    ("EARNINGS", ("earnings", "results", "10-q", "10-k", "실적", "잠정실적"), 0.85),
    ("GUIDANCE", ("guidance", "outlook", "forecast", "전망", "가이던스"), 0.80),
    ("M&A", ("merger", "acquisition", "acquire", "takeover", "합병", "인수"), 0.90),
    ("CAPITAL", ("offering", "issuance", "convertible", "capital raise", "증자", "유상증자", "전환사채"), 0.75),
    ("REGULATORY", ("sec", "regulator", "regulation", "antitrust", "공정위", "금융위", "규제"), 0.85),
    ("LEGAL", ("lawsuit", "litigation", "investigation", "소송", "조사"), 0.75),
    ("MANAGEMENT", ("ceo", "cfo", "resign", "appoint", "대표이사", "임원", "사임", "선임"), 0.70),
    ("PRODUCT", ("launch", "product", "approval", "fda", "출시", "승인"), 0.65),
    ("MACRO", ("cpi", "consumer price index", "inflation", "employment",
               "employment situation", "jobs", "jolts",
               "job openings and labor turnover", "fomc", "rate", "pce", "gdp",
               "물가", "고용", "금리", "통화정책", "기준금리"), 0.90),
    ("CRYPTO_REGULATORY", ("bitcoin etf", "ethereum etf", "crypto regulation", "stablecoin",
                           "가상자산", "비트코인 etf"), 0.85),
]

DEFAULT_CRYPTO_ALIASES = {
    "bitcoin": "BTC", "btc": "BTC", "btc-usd": "BTC",
    "ethereum": "ETH", "ether": "ETH", "eth": "ETH", "eth-usd": "ETH",
}


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt:
            return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
    except Exception:
        pass
    raw_text = text
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
    except Exception:
        pass
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(raw_text, fmt).replace(tzinfo=UTC)
        except Exception:
            pass
    return None


def clean_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        p = urlsplit(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))
    except Exception:
        return url.strip()


def stable_id(source: str, source_item_id: str | None, url: str | None,
              title: str, published_at: datetime | None) -> str:
    seed = "|".join([
        source.strip().lower(),
        (source_item_id or "").strip(),
        clean_url(url) or "",
        re.sub(r"\s+", " ", title).strip().lower(),
        iso(published_at) or "",
    ])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def event_classify(title: str, source: str, payload: dict[str, Any]) -> tuple[str, float]:
    lower = f"{title} {payload.get('form','')} {payload.get('report_nm','')}".lower()
    if source == "sec_edgar":
        form = str(payload.get("form") or "").upper()
        if form in {"10-Q", "10-K", "20-F", "40-F"}:
            return "EARNINGS", 0.95
        if form in {"8-K", "6-K"}:
            return "CORPORATE_DISCLOSURE", 0.90
    if source == "opendart":
        return "CORPORATE_DISCLOSURE", 0.90
    for kind, words, confidence in EVENT_RULES:
        if any(w in lower for w in words):
            return kind, confidence
    return "GENERAL_NEWS", 0.50


@dataclass(frozen=True)
class Entity:
    market: str
    symbol: str
    relevance: float
    mapping_method: str
    entity_type: str = "ASSET"
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class Article:
    article_id: str
    source: str
    source_item_id: str | None
    canonical_url: str | None
    title: str
    summary: str | None
    published_at: datetime | None
    first_seen_at: datetime
    available_at: datetime
    time_quality: str
    language: str | None
    content_sha256: str
    payload: dict[str, Any]
    entities: tuple[Entity, ...]


class Spool:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self._schema()

    def _schema(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS article (
            article_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_item_id TEXT,
            canonical_url TEXT,
            title TEXT NOT NULL,
            summary TEXT,
            published_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            available_at TEXT NOT NULL,
            time_quality TEXT NOT NULL,
            language TEXT,
            content_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            synced_neon INTEGER NOT NULL DEFAULT 0,
            synced_drive INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_article_neon ON article(synced_neon, first_seen_at);
        CREATE INDEX IF NOT EXISTS idx_article_drive ON article(synced_drive, first_seen_at);
        CREATE INDEX IF NOT EXISTS idx_article_source ON article(source, first_seen_at);
        CREATE TABLE IF NOT EXISTS entity (
            article_id TEXT NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            relevance REAL NOT NULL,
            mapping_method TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(article_id, market, symbol),
            FOREIGN KEY(article_id) REFERENCES article(article_id)
        );
        CREATE TABLE IF NOT EXISTS source_state (
            source TEXT PRIMARY KEY,
            last_attempt_at TEXT,
            last_success_at TEXT,
            etag TEXT,
            last_modified TEXT,
            cursor TEXT,
            last_error_at TEXT,
            last_error TEXT,
            rows_seen INTEGER NOT NULL DEFAULT 0,
            rows_inserted INTEGER NOT NULL DEFAULT 0,
            rows_duplicate INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        """)
        self.db.commit()

    def due(self, source: str, min_interval_seconds: int) -> bool:
        row = self.db.execute(
            "SELECT last_attempt_at FROM source_state WHERE source=?", (source,)
        ).fetchone()
        if not row or not row["last_attempt_at"]:
            return True
        dt = parse_dt(row["last_attempt_at"])
        return not dt or (utc_now() - dt).total_seconds() >= min_interval_seconds

    def source_state(self, source: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM source_state WHERE source=?", (source,)).fetchone()
        return dict(row) if row else {}

    def record_source(self, source: str, *, success: bool, seen: int = 0,
                      inserted: int = 0, duplicates: int = 0,
                      etag: str | None = None, last_modified: str | None = None,
                      cursor: str | None = None, error: str | None = None,
                      payload: dict[str, Any] | None = None) -> None:
        now = iso(utc_now())
        old = self.source_state(source)
        self.db.execute("""
        INSERT INTO source_state(
          source,last_attempt_at,last_success_at,etag,last_modified,cursor,
          last_error_at,last_error,rows_seen,rows_inserted,rows_duplicate,payload_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(source) DO UPDATE SET
          last_attempt_at=excluded.last_attempt_at,
          last_success_at=CASE WHEN excluded.last_success_at IS NOT NULL
                               THEN excluded.last_success_at ELSE source_state.last_success_at END,
          etag=COALESCE(excluded.etag,source_state.etag),
          last_modified=COALESCE(excluded.last_modified,source_state.last_modified),
          cursor=COALESCE(excluded.cursor,source_state.cursor),
          last_error_at=excluded.last_error_at,
          last_error=excluded.last_error,
          rows_seen=source_state.rows_seen+excluded.rows_seen,
          rows_inserted=source_state.rows_inserted+excluded.rows_inserted,
          rows_duplicate=source_state.rows_duplicate+excluded.rows_duplicate,
          payload_json=excluded.payload_json
        """, (
            source, now, now if success else None,
            etag or old.get("etag"), last_modified or old.get("last_modified"),
            cursor or old.get("cursor"), None if success else now,
            None if success else error, seen, inserted, duplicates,
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
        ))
        self.db.commit()

    def record_disabled(self, source: str, reason: str) -> None:
        now = iso(utc_now())
        old = self.source_state(source)
        self.db.execute("""
        INSERT INTO source_state(
          source,last_attempt_at,last_success_at,etag,last_modified,cursor,
          last_error_at,last_error,rows_seen,rows_inserted,rows_duplicate,payload_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(source) DO UPDATE SET
          last_attempt_at=excluded.last_attempt_at,
          last_success_at=source_state.last_success_at,
          etag=source_state.etag,
          last_modified=source_state.last_modified,
          cursor=source_state.cursor,
          last_error_at=NULL,
          last_error=NULL,
          rows_seen=source_state.rows_seen,
          rows_inserted=source_state.rows_inserted,
          rows_duplicate=source_state.rows_duplicate,
          payload_json=excluded.payload_json
        """, (
            source, now, old.get("last_success_at"), old.get("etag"),
            old.get("last_modified"), old.get("cursor"), None, None,
            0, 0, 0,
            json.dumps({"status": "DISABLED", "reason": reason}, sort_keys=True),
        ))
        self.db.commit()

    def put(self, article: Article) -> bool:
        cur = self.db.execute(
            "SELECT 1 FROM article WHERE article_id=?", (article.article_id,)
        ).fetchone()
        is_new = cur is None
        if is_new:
            self.db.execute("""
            INSERT INTO article(
              article_id,source,source_item_id,canonical_url,title,summary,published_at,
              first_seen_at,last_seen_at,available_at,time_quality,language,
              content_sha256,payload_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                article.article_id, article.source, article.source_item_id,
                article.canonical_url, article.title, article.summary,
                iso(article.published_at), iso(article.first_seen_at),
                iso(article.first_seen_at), iso(article.available_at),
                article.time_quality, article.language, article.content_sha256,
                json.dumps(article.payload, ensure_ascii=False, sort_keys=True),
            ))
        else:
            self.db.execute(
                "UPDATE article SET last_seen_at=? WHERE article_id=?",
                (iso(utc_now()), article.article_id),
            )
        for e in article.entities:
            self.db.execute("""
            INSERT INTO entity(article_id,market,symbol,entity_type,relevance,mapping_method,payload_json)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(article_id,market,symbol) DO UPDATE SET
              relevance=MAX(entity.relevance,excluded.relevance),
              mapping_method=excluded.mapping_method,
              payload_json=excluded.payload_json
            """, (
                article.article_id, e.market, e.symbol, e.entity_type, e.relevance,
                e.mapping_method, json.dumps(e.payload or {}, ensure_ascii=False, sort_keys=True),
            ))
        self.db.commit()
        return is_new

    def pending(self, destination: str, limit: int) -> list[sqlite3.Row]:
        col = "synced_neon" if destination == "neon" else "synced_drive"
        return self.db.execute(
            f"SELECT * FROM article WHERE {col}=0 ORDER BY first_seen_at LIMIT ?",
            (limit,),
        ).fetchall()

    def entities(self, article_id: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM entity WHERE article_id=? ORDER BY market,symbol",
            (article_id,),
        ).fetchall()

    def mark(self, destination: str, ids: Iterable[str]) -> None:
        ids = list(ids)
        if not ids:
            return
        col = "synced_neon" if destination == "neon" else "synced_drive"
        self.db.executemany(
            f"UPDATE article SET {col}=1 WHERE article_id=?",
            [(x,) for x in ids],
        )
        self.db.commit()

    def stats(self) -> dict[str, Any]:
        row = self.db.execute("""
          SELECT count(*) AS articles,
                 sum(CASE WHEN synced_neon=0 THEN 1 ELSE 0 END) AS pending_neon,
                 sum(CASE WHEN synced_drive=0 THEN 1 ELSE 0 END) AS pending_drive,
                 min(first_seen_at) AS first_seen_at,
                 max(first_seen_at) AS last_seen_at
          FROM article
        """).fetchone()
        return dict(row)


def load_env() -> None:
    env_path = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
    if env_path.exists():
        load_dotenv(env_path, override=True)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def http_get(url: str, *, headers: dict[str, str] | None = None,
             params: dict[str, Any] | None = None, timeout: float = 30,
             retries: int = 3) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                r = client.get(url, headers=headers, params=params)
            if r.status_code == 304:
                return r
            if r.status_code == 429:
                retry_after_seconds: float | None = None
                retry_after = (r.headers.get("Retry-After") or "").strip()
                if retry_after:
                    try:
                        retry_after_seconds = max(0.0, float(retry_after))
                    except ValueError:
                        retry_at = parse_dt(retry_after)
                        if retry_at is not None:
                            retry_after_seconds = max(
                                0.0, (retry_at - utc_now()).total_seconds()
                            )
                raise HttpRateLimitError(url, retry_after_seconds)
            if r.status_code in {401, 403}:
                raise HttpAccessDeniedError(url, r.status_code)
            r.raise_for_status()
            return r
        except (HttpRateLimitError, HttpAccessDeniedError):
            # Provider-side policy responses are not transport failures. Immediate
            # retries only increase the chance of a longer block.
            raise
        except Exception as exc:
            last = exc
            if attempt == retries:
                break
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last}") from last


def parse_feed(raw: bytes, source: str, entities: tuple[Entity, ...],
               language: str | None = None) -> list[Article]:
    now = utc_now()
    root = ET.fromstring(raw)
    out: list[Article] = []
    items = root.findall(".//item")
    if items:
        for item in items:
            def t(name: str) -> str | None:
                x = item.find(name)
                return (x.text or "").strip() if x is not None and x.text else None
            title = t("title") or "(untitled)"
            url = clean_url(t("link"))
            sid = t("guid") or url
            published = parse_dt(t("pubDate") or t("date"))
            summary = t("description")
            quality = "PUBLISHER_TS" if published else "FIRST_SEEN_TS"
            available = max(published, now) if published and published > now else (published or now)
            payload = {"feed_source": source}
            aid = stable_id(source, sid, url, title, published)
            out.append(Article(
                aid, source, sid, url, title, summary, published, now, available,
                quality, language,
                hashlib.sha256(raw + aid.encode()).hexdigest(), payload, entities
            ))
        return out

    for entry in root.findall(".//{*}entry"):
        def atag(name: str) -> str | None:
            x = entry.find(f"{{*}}{name}")
            return (x.text or "").strip() if x is not None and x.text else None
        title = atag("title") or "(untitled)"
        links = entry.findall("{*}link")
        url = None
        for link in links:
            href = link.attrib.get("href")
            if href:
                url = clean_url(href)
                if link.attrib.get("rel", "alternate") == "alternate":
                    break
        sid = atag("id") or url
        published = parse_dt(atag("published") or atag("updated"))
        summary = atag("summary") or atag("content")
        quality = "PUBLISHER_TS" if published else "FIRST_SEEN_TS"
        available = max(published, now) if published and published > now else (published or now)
        aid = stable_id(source, sid, url, title, published)
        out.append(Article(
            aid, source, sid, url, title, summary, published, now, available,
            quality, language,
            hashlib.sha256(raw + aid.encode()).hexdigest(),
            {"feed_source": source}, entities
        ))
    return out


def latest_universe(db_url: str | None, cache_path: Path) -> dict[str, list[str]]:
    if db_url:
        try:
            with psycopg.connect(db_url, connect_timeout=10) as conn:
                rows = conn.execute("""
                WITH latest AS (
                  SELECT market, max(as_of) AS mx
                  FROM public.model_output
                  WHERE market IN ('US','KR','CRYPTO')
                  GROUP BY market
                )
                SELECT m.market,m.symbol
                FROM public.model_output m
                JOIN latest l ON l.market=m.market AND l.mx=m.as_of
                GROUP BY m.market,m.symbol
                ORDER BY m.market,m.symbol
                """).fetchall()
            data: dict[str, list[str]] = {"US": [], "KR": [], "CRYPTO": []}
            for market, symbol in rows:
                data[str(market)].append(str(symbol))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        except Exception as exc:
            print(f"[NEWS][WARN] Neon universe refresh failed: {exc}")
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    def env_list(name: str) -> list[str]:
        return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]
    return {
        "US": env_list("KALMAN_NEWS_US_SYMBOLS"),
        "KR": env_list("KALMAN_NEWS_KR_SYMBOLS"),
        "CRYPTO": env_list("KALMAN_NEWS_CRYPTO_SYMBOLS") or ["BTC", "ETH"],
    }


def sec_company_map(state_dir: Path, user_agent: str, max_age_hours: int = 24) -> dict[str, dict[str, Any]]:
    path = state_dir / "sec_company_tickers.json"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600
    if not fresh:
        try:
            r = http_get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            json.loads(tmp.read_text(encoding="utf-8"))
            os.replace(tmp, path)
        except Exception as exc:
            if not path.exists():
                raise
            print(f"[NEWS][WARN] SEC ticker map refresh failed; stale cache used: {exc}")
    obj = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(v["ticker"]).upper(): {
            "cik": str(v["cik_str"]).zfill(10),
            "title": str(v.get("title") or ""),
        }
        for v in obj.values()
    }


def dart_company_map(state_dir: Path, api_key: str, max_age_hours: int = 24) -> dict[str, str]:
    path = state_dir / "dart_corp_map.json"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600
    if fresh:
        return json.loads(path.read_text(encoding="utf-8"))
    r = http_get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": api_key})
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        if not names:
            raise RuntimeError("OpenDART corpCode archive is empty")
        root = ET.fromstring(zf.read(names[0]))
    mapping: dict[str, str] = {}
    for item in root.findall(".//list"):
        stock = (item.findtext("stock_code") or "").strip()
        name = (item.findtext("corp_name") or "").strip()
        if stock and name:
            mapping[stock] = name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return mapping


def alias_entities(title: str, universe: dict[str, list[str]],
                   secmap: dict[str, dict[str, Any]] | None,
                   dartmap: dict[str, str] | None,
                   market_hint: str) -> tuple[Entity, ...]:
    low = title.lower()
    entities: dict[tuple[str, str], Entity] = {}
    if market_hint == "CRYPTO":
        for alias, symbol in DEFAULT_CRYPTO_ALIASES.items():
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low):
                entities[("CRYPTO", symbol)] = Entity("CRYPTO", symbol, 0.95, "crypto_alias_v1")
    if market_hint == "US" and secmap:
        allowed = set(universe.get("US", []))
        for symbol, meta in secmap.items():
            if symbol not in allowed:
                continue
            company = str(meta.get("title") or "").strip().lower()
            ticker_hit = re.search(rf"(?<![a-z0-9]){re.escape(symbol.lower())}(?![a-z0-9])", low)
            company_hit = len(company) >= 4 and company in low
            if company_hit or ticker_hit:
                entities[("US", symbol)] = Entity(
                    "US", symbol, 0.95 if company_hit else 0.75,
                    "sec_company_alias_v1"
                )
    if market_hint == "KR" and dartmap:
        allowed = set(universe.get("KR", []))
        for symbol, company in dartmap.items():
            if symbol not in allowed:
                continue
            if len(company) >= 2 and company.lower() in low:
                entities[("KR", symbol)] = Entity("KR", symbol, 0.95, "dart_company_alias_v1")
    if entities:
        return tuple(entities.values())
    if market_hint in MARKETS:
        fallback_symbol = {
            "US": "US_NEWS", "KR": "KR_NEWS", "CRYPTO": "CRYPTO_NEWS", "GLOBAL": "GLOBAL"
        }[market_hint]
        return (Entity(market_hint, fallback_symbol, 0.25, "market_topic_fallback_v1", "MARKET"),)
    return ()


def collect_rss(spool: Spool, cfg: dict[str, Any]) -> tuple[int, int]:
    source = cfg["name"]
    if not spool.due(source, int(cfg.get("min_interval_seconds", 300))):
        return 0, 0
    state = spool.source_state(source)
    headers: dict[str, str] = {"User-Agent": os.environ.get("KALMAN_NEWS_USER_AGENT", "KalmanNews/1.0")}
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    try:
        r = http_get(cfg["url"], headers=headers)
        if r.status_code == 304:
            spool.record_source(source, success=True, payload={"result": "not_modified"})
            return 0, 0
        scope = str(cfg.get("market", "GLOBAL")).upper()
        symbol = str(cfg.get("symbol") or ("GLOBAL" if scope == "GLOBAL" else f"{scope}_MACRO"))
        ents = (Entity(scope, symbol, 1.0, "official_feed_v1", "MACRO"),)
        rows = parse_feed(r.content, source, ents, cfg.get("language"))
        inserted = sum(1 for a in rows if spool.put(a))
        spool.record_source(
            source, success=True, seen=len(rows), inserted=inserted,
            duplicates=len(rows) - inserted,
            etag=r.headers.get("etag"), last_modified=r.headers.get("last-modified"),
            payload={"url": cfg["url"], "market": scope},
        )
        return len(rows), inserted
    except Exception as exc:
        spool.record_source(source, success=False, error=str(exc), payload={"url": cfg["url"]})
        print(f"[NEWS][WARN] {source}: {exc}")
        return 0, 0


def collect_sec(spool: Spool, cfg: dict[str, Any], universe: dict[str, list[str]],
                state_dir: Path) -> tuple[int, int]:
    source = "sec_edgar"
    if not cfg.get("enabled", True):
        spool.record_disabled(source, "config_disabled")
        return 0, 0
    if not env_bool("KALMAN_NEWS_SEC_ENABLED", True):
        spool.record_disabled(source, "runtime_gate")
        return 0, 0
    if not spool.due(source, int(cfg.get("min_interval_seconds", 900))):
        return 0, 0
    ua = os.environ.get("KALMAN_NEWS_SEC_USER_AGENT", "").strip()
    if not ua:
        spool.record_source(source, success=False, error="KALMAN_NEWS_SEC_USER_AGENT is not set")
        return 0, 0
    try:
        mapping = sec_company_map(state_dir, ua)
        forms = {str(x).upper() for x in cfg.get("forms", [])}
        seen = inserted = 0
        cutoff = utc_now() - timedelta(days=int(cfg.get("lookback_days", 2)))
        for symbol in universe.get("US", []):
            meta = mapping.get(symbol)
            if not meta:
                continue
            r = http_get(
                f"https://data.sec.gov/submissions/CIK{meta['cik']}.json",
                headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
            )
            recent = r.json().get("filings", {}).get("recent", {})
            keys = list(recent.keys())
            if not keys:
                continue
            n = len(recent.get("accessionNumber", []))
            for i in range(min(n, int(cfg.get("max_recent_per_company", 30)))):
                row = {k: recent[k][i] for k in keys if isinstance(recent.get(k), list) and i < len(recent[k])}
                form = str(row.get("form") or "").upper()
                if forms and form not in forms:
                    continue
                accepted = parse_dt(row.get("acceptanceDateTime"))
                filing_date = str(row.get("filingDate") or "")
                if accepted and accepted < cutoff:
                    continue
                if not accepted and filing_date:
                    fd = parse_dt(filing_date + "T00:00:00+00:00")
                    if fd and fd < cutoff:
                        continue
                accession = str(row.get("accessionNumber") or "")
                primary = str(row.get("primaryDocument") or "")
                accession_path = accession.replace("-", "")
                cik_int = str(int(meta["cik"]))
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_path}/{primary}"
                    if accession and primary else None
                )
                title = f"{symbol} {form} {row.get('primaryDocDescription') or ''}".strip()
                now = utc_now()
                quality = "EXACT_SOURCE_TS" if accepted else "FIRST_SEEN_TS"
                available = accepted or now
                payload = {"symbol": symbol, "company": meta["title"], **row}
                aid = stable_id(source, accession or None, url, title, accepted)
                article = Article(
                    aid, source, accession or None, clean_url(url), title, None,
                    accepted, now, available, quality, "en",
                    hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest(),
                    payload, (Entity("US", symbol, 1.0, "sec_direct_v1"),)
                )
                seen += 1
                inserted += int(spool.put(article))
            time.sleep(float(cfg.get("request_sleep_seconds", 0.12)))
        spool.record_source(source, success=True, seen=seen, inserted=inserted,
                            duplicates=seen-inserted, payload={"symbols": len(universe.get("US", []))})
        return seen, inserted
    except Exception as exc:
        spool.record_source(source, success=False, error=str(exc))
        print(f"[NEWS][WARN] {source}: {exc}")
        return 0, 0


def collect_dart(spool: Spool, cfg: dict[str, Any], universe: dict[str, list[str]]) -> tuple[int, int]:
    source = "opendart"
    if not cfg.get("enabled", True):
        spool.record_disabled(source, "config_disabled")
        return 0, 0
    if not env_bool("KALMAN_NEWS_DART_ENABLED", True):
        spool.record_disabled(source, "runtime_gate")
        return 0, 0
    if not spool.due(source, int(cfg.get("min_interval_seconds", 300))):
        return 0, 0
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        spool.record_source(source, success=False, error="DART_API_KEY is not set")
        return 0, 0
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
        allowed = set(universe.get("KR", []))
        seen = inserted = 0
        page = 1
        while page <= int(cfg.get("max_pages", 20)):
            r = http_get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": key, "bgn_de": today, "end_de": today,
                    "page_no": page, "page_count": int(cfg.get("page_count", 100)),
                },
            )
            obj = r.json()
            status = str(obj.get("status") or "")
            if status == "013":
                break
            if status != "000":
                raise RuntimeError(f"OpenDART status={status}: {obj.get('message')}")
            rows = obj.get("list") or []
            for row in rows:
                symbol = str(row.get("stock_code") or "").strip()
                if not symbol or (allowed and symbol not in allowed):
                    continue
                receipt = str(row.get("rcept_no") or "")
                title = str(row.get("report_nm") or "(untitled)")
                company = str(row.get("corp_name") or "")
                url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}" if receipt else None
                now = utc_now()
                payload = {**row, "company": company}
                aid = stable_id(source, receipt or None, url, f"{company} {title}", None)
                article = Article(
                    aid, source, receipt or None, clean_url(url),
                    f"{company} | {title}", None, None, now, now,
                    "FIRST_SEEN_TS", "ko",
                    hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                    payload, (Entity("KR", symbol, 1.0, "dart_direct_v1"),)
                )
                seen += 1
                inserted += int(spool.put(article))
            total_page = int(obj.get("total_page") or page)
            if page >= total_page:
                break
            page += 1
        spool.record_source(source, success=True, seen=seen, inserted=inserted,
                            duplicates=seen-inserted, cursor=today,
                            payload={"date_kst": today, "symbols": len(allowed)})
        return seen, inserted
    except Exception as exc:
        spool.record_source(source, success=False, error=str(exc))
        print(f"[NEWS][WARN] {source}: {exc}")
        return 0, 0


def collect_gdelt(spool: Spool, cfg: dict[str, Any], universe: dict[str, list[str]],
                  secmap: dict[str, dict[str, Any]] | None,
                  dartmap: dict[str, str] | None) -> tuple[int, int]:
    if not cfg.get("enabled", True):
        return 0, 0
    total_seen = total_inserted = 0
    last_request_monotonic: float | None = None
    request_spacing = max(0.0, float(cfg.get("request_spacing_seconds", 8)))
    for item in cfg.get("queries", []):
        market = str(item["market"]).upper()
        source = f"gdelt_{market.lower()}"
        if not spool.due(source, int(cfg.get("min_interval_seconds", 900))):
            continue
        try:
            if last_request_monotonic is not None and request_spacing > 0:
                elapsed = time.monotonic() - last_request_monotonic
                if elapsed < request_spacing:
                    time.sleep(request_spacing - elapsed)
            last_request_monotonic = time.monotonic()
            r = http_get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": item["query"],
                    "mode": "ArtList",
                    "maxrecords": int(cfg.get("maxrecords", 250)),
                    "format": "json",
                    "sort": "DateDesc",
                    "timespan": str(cfg.get("timespan", "1h")),
                },
                timeout=float(cfg.get("timeout_seconds", 45)),
            )
            obj = r.json()
            rows = obj.get("articles") or []
            inserted = 0
            for row in rows:
                title = str(row.get("title") or "(untitled)")
                url = clean_url(str(row.get("url") or "")) or None
                published = parse_dt(row.get("seendate"))
                now = utc_now()
                entities = alias_entities(title, universe, secmap, dartmap, market)
                payload = {k: v for k, v in row.items() if k not in {"title"}}
                aid = stable_id(source, None, url, title, published)
                article = Article(
                    aid, source, None, url, title, None, published, now,
                    published or now, "GDELT_OBSERVED_PROXY",
                    str(row.get("language") or "") or None,
                    hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest(),
                    payload, entities
                )
                inserted += int(spool.put(article))
            spool.record_source(
                source, success=True, seen=len(rows), inserted=inserted,
                duplicates=len(rows)-inserted, payload={"market": market, "query": item["query"]},
            )
            total_seen += len(rows)
            total_inserted += inserted
        except HttpRateLimitError as exc:
            spool.record_source(
                source, success=False, error=str(exc),
                payload={
                    "market": market,
                    "query": item.get("query"),
                    "retry_after_seconds": exc.retry_after_seconds,
                    "rate_limited": True,
                },
            )
            print(f"[NEWS][WARN] {source}: {exc}; remaining GDELT queries deferred")
            break
        except Exception as exc:
            spool.record_source(source, success=False, error=str(exc),
                                payload={"market": market, "query": item.get("query")})
            print(f"[NEWS][WARN] {source}: {exc}")
    return total_seen, total_inserted


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def source_market_scope(source: str) -> list[str]:
    if source == "sec_edgar" or source == "gdelt_us":
        return ["US"]
    if source == "opendart" or source.startswith("bok_") or source == "gdelt_kr":
        return ["KR"]
    if source == "gdelt_crypto" or source.startswith("gdelt_historical"):
        return ["CRYPTO"]
    return ["GLOBAL"]


def sync_neon(spool: Spool, db_url: str | None, batch_size: int = 500) -> int:
    if not env_bool("KALMAN_NEWS_NEON_SYNC_ENABLED", False):
        print("[NEWS][SYNC] Neon sync disabled by KALMAN_NEWS_NEON_SYNC_ENABLED")
        return 0
    if not db_url:
        print("[NEWS][SYNC][WARN] DATABASE_URL_WRITER missing; Neon sync skipped")
        return 0
    rows = spool.pending("neon", batch_size)
    ids: list[str] = []
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.transaction():
            for row in rows:
                payload = json.loads(row["payload_json"])
                conn.execute("""
                INSERT INTO public.news_article(
                  article_id,source,source_item_id,canonical_url,title,summary,published_at,
                  first_seen_at,available_at,time_quality,language,content_sha256,payload,updated_at
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
                ON CONFLICT(article_id) DO UPDATE SET
                  first_seen_at=LEAST(news_article.first_seen_at,excluded.first_seen_at),
                  updated_at=now()
                """, (
                    row["article_id"], row["source"], row["source_item_id"], row["canonical_url"],
                    row["title"], row["summary"], row["published_at"], row["first_seen_at"],
                    row["available_at"], row["time_quality"], row["language"],
                    row["content_sha256"], json.dumps(payload, ensure_ascii=False),
                ))
                for e in spool.entities(row["article_id"]):
                    conn.execute("""
                    INSERT INTO public.news_entity(
                      article_id,market,symbol,entity_type,relevance,mapping_method,payload
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT(article_id,market,symbol) DO UPDATE SET
                      relevance=GREATEST(news_entity.relevance,excluded.relevance),
                      mapping_method=excluded.mapping_method,
                      payload=excluded.payload
                    """, (
                        row["article_id"], e["market"], e["symbol"], e["entity_type"],
                        e["relevance"], e["mapping_method"], e["payload_json"],
                    ))
                event_type, confidence = event_classify(row["title"], row["source"], payload)
                conn.execute("""
                INSERT INTO public.news_event(article_id,event_type,importance,confidence,model_version,payload)
                VALUES(%s,%s,%s,%s,'news-event-rules-v1','{}'::jsonb)
                ON CONFLICT(article_id,event_type,model_version) DO NOTHING
                """, (row["article_id"], event_type, confidence, confidence))
                ids.append(row["article_id"])
        states = spool.db.execute("SELECT * FROM source_state").fetchall()
        with conn.transaction():
            for s in states:
                payload = s["payload_json"] or "{}"
                conn.execute("""
                INSERT INTO public.news_source_state(
                  source,market_scope,last_attempt_at,last_success_at,etag,last_modified,cursor,
                  last_error_at,last_error,rows_seen,rows_inserted,rows_duplicate,payload,updated_at
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
                ON CONFLICT(source) DO UPDATE SET
                  market_scope=excluded.market_scope,
                  last_attempt_at=excluded.last_attempt_at,
                  last_success_at=excluded.last_success_at,
                  etag=excluded.etag,last_modified=excluded.last_modified,cursor=excluded.cursor,
                  last_error_at=excluded.last_error_at,last_error=excluded.last_error,
                  rows_seen=excluded.rows_seen,rows_inserted=excluded.rows_inserted,
                  rows_duplicate=excluded.rows_duplicate,payload=excluded.payload,updated_at=now()
                """, (
                    s["source"], source_market_scope(s["source"]), s["last_attempt_at"],
                    s["last_success_at"], s["etag"], s["last_modified"], s["cursor"],
                    s["last_error_at"], s["last_error"], s["rows_seen"], s["rows_inserted"],
                    s["rows_duplicate"], payload,
                ))
    spool.mark("neon", ids)
    return len(ids)


def drive_mount_available(mount: Path) -> bool:
    try:
        return mount.exists() and mount.is_mount() and next(mount.iterdir(), None) is not None
    except Exception:
        return False


def sync_drive(spool: Spool, drive_root: Path, batch_size: int = 1000) -> int:
    if not env_bool("KALMAN_NEWS_DRIVE_SYNC_ENABLED", True):
        print("[NEWS][SYNC] Drive sync disabled by KALMAN_NEWS_DRIVE_SYNC_ENABLED")
        return 0
    mount = Path(os.environ.get("KALMAN_GDRIVE_MOUNT", "/mnt/gdrive"))
    if str(drive_root).startswith(str(mount)) and not drive_mount_available(mount):
        print(f"[NEWS][SYNC][WARN] Drive mount unavailable: {mount}; archive sync deferred")
        return 0
    rows = spool.pending("drive", batch_size)
    if not rows:
        return 0
    now = utc_now()
    folder = drive_root / f"{now:%Y/%m/%d}"
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256("".join(r["article_id"] for r in rows).encode()).hexdigest()[:12]
    path = folder / f"news_{now:%Y%m%dT%H%M%SZ}_{digest}.jsonl.gz"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for row in rows:
            obj = dict(row)
            obj["payload"] = json.loads(obj.pop("payload_json"))
            obj["entities"] = [
                {**dict(e), "payload": json.loads(e["payload_json"])}
                for e in spool.entities(row["article_id"])
            ]
            for e in obj["entities"]:
                e.pop("payload_json", None)
            obj.pop("synced_neon", None)
            obj.pop("synced_drive", None)
            fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)
    spool.mark("drive", [r["article_id"] for r in rows])
    return len(rows)


def write_coverage(spool: Spool, db_url: str | None, output: Path) -> dict[str, Any]:
    now = utc_now()
    states = [dict(r) for r in spool.db.execute("SELECT * FROM source_state ORDER BY source")]
    stats = spool.stats()
    report = {
        "generated_at_utc": iso(now),
        "spool": stats,
        "sources": states,
        "status": "READY" if states and any(s.get("last_success_at") for s in states) else "NO_SUCCESS_YET",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, output)

    if db_url:
        try:
            hour = now.replace(minute=0, second=0, microsecond=0)
            with psycopg.connect(db_url, connect_timeout=15) as conn:
                rows = conn.execute("""
                SELECT e.market,a.source,
                       count(DISTINCT a.article_id)::int AS articles,
                       count(DISTINCT e.article_id)::int AS mapped_articles,
                       count(DISTINCT e.symbol)::int AS unique_symbols,
                       percentile_cont(0.5) WITHIN GROUP (
                         ORDER BY GREATEST(0,extract(epoch FROM (a.first_seen_at-a.published_at)))
                       ) FILTER (WHERE a.published_at IS NOT NULL) AS latency_p50,
                       percentile_cont(0.95) WITHIN GROUP (
                         ORDER BY GREATEST(0,extract(epoch FROM (a.first_seen_at-a.published_at)))
                       ) FILTER (WHERE a.published_at IS NOT NULL) AS latency_p95,
                       avg(CASE WHEN a.time_quality IN ('EXACT_SOURCE_TS','PUBLISHER_TS') THEN 1.0 ELSE 0.0 END) AS exact_ratio
                FROM public.news_article a
                JOIN public.news_entity e USING(article_id)
                WHERE a.first_seen_at >= %s
                GROUP BY e.market,a.source
                """, (hour,)).fetchall()
                for market, source, articles, mapped, symbols, p50, p95, exact in rows:
                    conn.execute("""
                    INSERT INTO public.news_coverage_hourly(
                      as_of,market,source,articles,mapped_articles,unique_symbols,
                      duplicate_count,duplicate_ratio,unmapped_ratio,
                      latency_p50_seconds,latency_p95_seconds,exact_ts_ratio,quality_flag,payload
                    ) VALUES(%s,%s,%s,%s,%s,%s,0,0,0,%s,%s,%s,'OBSERVED','{}'::jsonb)
                    ON CONFLICT(as_of,market,source) DO UPDATE SET
                      articles=excluded.articles,mapped_articles=excluded.mapped_articles,
                      unique_symbols=excluded.unique_symbols,
                      latency_p50_seconds=excluded.latency_p50_seconds,
                      latency_p95_seconds=excluded.latency_p95_seconds,
                      exact_ts_ratio=excluded.exact_ts_ratio,quality_flag=excluded.quality_flag
                    """, (hour, market, source, articles, mapped, symbols, p50, p95, exact))
                conn.commit()
        except Exception as exc:
            print(f"[NEWS][COVERAGE][WARN] Neon coverage write failed: {exc}")
    return report


def import_gdelt_csv(spool: Spool, path: Path) -> tuple[int, int]:
    seen = inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            source = "gdelt_historical"
            title = row.get("title") or "(untitled)"
            url = clean_url(row.get("canonical_url"))
            published = parse_dt(row.get("published_at_utc"))
            available = parse_dt(row.get("available_decision_time_utc")) or published or utc_now()
            market = "CRYPTO" if str(row.get("is_crypto_relevant")).lower() == "true" else "GLOBAL"
            symbol = "BTC" if str(row.get("is_btc_related")).lower() == "true" else (
                "CRYPTO_NEWS" if market == "CRYPTO" else "GLOBAL"
            )
            payload = dict(row)
            sid = row.get("article_key") or row.get("raw_guid")
            aid = stable_id(source, sid, url, title, published)
            article = Article(
                aid, source, sid, url, title, row.get("summary") or None,
                published, utc_now(), available, "GDELT_OBSERVED_PROXY", None,
                hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                payload, (Entity(market, symbol, 0.7, "historical_import_v1"),)
            )
            seen += 1
            inserted += int(spool.put(article))
    spool.record_source("gdelt_historical_import", success=True, seen=seen, inserted=inserted,
                        duplicates=seen-inserted, payload={"path": str(path)})
    return seen, inserted


def collect_all(spool: Spool, config: dict[str, Any], db_url: str | None,
                state_dir: Path) -> dict[str, Any]:
    universe = latest_universe(db_url, state_dir / "universe_cache.json")
    sec_cfg = config.get("sec", {})
    dart_cfg = config.get("dart", {})
    gdelt_cfg = config.get("gdelt", {})
    secmap = None
    dartmap = None
    sec_enabled = bool(sec_cfg.get("enabled", True)) and env_bool("KALMAN_NEWS_SEC_ENABLED", True)
    dart_enabled = bool(dart_cfg.get("enabled", True)) and env_bool("KALMAN_NEWS_DART_ENABLED", True)
    sec_due = sec_enabled and spool.due("sec_edgar", int(sec_cfg.get("min_interval_seconds", 900)))
    dart_due = dart_enabled and spool.due("opendart", int(dart_cfg.get("min_interval_seconds", 300)))
    gdelt_kr_due = spool.due("gdelt_kr", int(gdelt_cfg.get("min_interval_seconds", 900)))

    # Never touch SEC endpoints while the runtime SEC gate is disabled. GDELT US
    # can continue with market-level fallback mapping until SEC access is restored.
    if os.environ.get("KALMAN_NEWS_SEC_USER_AGENT") and sec_due:
        try:
            secmap = sec_company_map(state_dir, os.environ["KALMAN_NEWS_SEC_USER_AGENT"])
        except Exception as exc:
            print(f"[NEWS][WARN] SEC company alias cache: {exc}")
    if dart_enabled and os.environ.get("DART_API_KEY") and (dart_due or gdelt_kr_due):
        try:
            dartmap = dart_company_map(state_dir, os.environ["DART_API_KEY"])
        except Exception as exc:
            print(f"[NEWS][WARN] DART company alias cache: {exc}")

    totals = {"seen": 0, "inserted": 0}
    for rss in config.get("rss_sources", []):
        if rss.get("enabled", True):
            a, b = collect_rss(spool, rss)
            totals["seen"] += a
            totals["inserted"] += b
    for fn, args in [
        (collect_sec, (spool, sec_cfg, universe, state_dir)),
        (collect_dart, (spool, dart_cfg, universe)),
        (collect_gdelt, (spool, gdelt_cfg, universe, secmap, dartmap)),
    ]:
        a, b = fn(*args)
        totals["seen"] += a
        totals["inserted"] += b
    totals["universe"] = {k: len(v) for k, v in universe.items()}
    return totals


def selftest() -> None:
    sample = b"""<?xml version="1.0"?><rss><channel><item>
    <title>Consumer Price Index update</title>
    <link>https://example.com/a?utm_source=x</link>
    <guid>abc</guid><pubDate>Fri, 18 Sep 2026 12:30:00 GMT</pubDate>
    <description>sample</description></item></channel></rss>"""
    a = parse_feed(sample, "test_rss", (Entity("GLOBAL", "GLOBAL", 1.0, "test"),))[0]
    assert a.canonical_url == "https://example.com/a"
    assert a.time_quality == "PUBLISHER_TS"
    assert event_classify(a.title, a.source, {})[0] == "MACRO"
    tmp = Path("/tmp/kalman-news-selftest.sqlite3")
    tmp.unlink(missing_ok=True)
    s = Spool(tmp)
    assert s.put(a) is True
    assert s.put(a) is False
    assert s.stats()["articles"] == 1
    tmp.unlink(missing_ok=True)
    print("NEWS_INGEST_V1_SELFTEST_OK")


def main() -> None:
    load_env()
    p = argparse.ArgumentParser(description="Kalman News/Event ingestion v1")
    p.add_argument("command", choices=["collect", "sync", "coverage", "import-gdelt-csv", "selftest"])
    p.add_argument("--config", default=os.environ.get("KALMAN_NEWS_CONFIG", "/opt/kalman/app/config/news-ingest-v1.json"))
    p.add_argument("--spool", default=os.environ.get("KALMAN_NEWS_SPOOL_DB", "/var/lib/kalman/news/news_spool.sqlite3"))
    p.add_argument("--state-dir", default=os.environ.get("KALMAN_NEWS_STATE_DIR", "/opt/kalman/state/news"))
    p.add_argument("--drive-root", default=os.environ.get("KALMAN_NEWS_DRIVE_ROOT", "/mnt/gdrive/Market_News/v1/raw"))
    p.add_argument("--coverage-output", default=os.environ.get("KALMAN_NEWS_COVERAGE_STATUS", "/opt/kalman/state/news/coverage_status.json"))
    p.add_argument("--input-csv")
    p.add_argument("--sync-neon", action="store_true")
    p.add_argument("--sync-drive", action="store_true")
    args = p.parse_args()

    if args.command == "selftest":
        selftest()
        return

    config = load_config(Path(args.config))
    spool = Spool(Path(args.spool))
    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")

    if args.command == "collect":
        result = collect_all(spool, config, db_url, Path(args.state_dir))
        print("[NEWS][COLLECT]", json.dumps(result, sort_keys=True))
        if args.sync_neon:
            print(f"[NEWS][SYNC] neon={sync_neon(spool, db_url)}")
        if args.sync_drive:
            print(f"[NEWS][SYNC] drive={sync_drive(spool, Path(args.drive_root))}")
    elif args.command == "sync":
        n = sync_neon(spool, db_url)
        d = sync_drive(spool, Path(args.drive_root))
        print(f"[NEWS][SYNC] neon={n} drive={d} pending={json.dumps(spool.stats(), sort_keys=True)}")
    elif args.command == "coverage":
        report = write_coverage(spool, db_url, Path(args.coverage_output))
        print("[NEWS][COVERAGE]", json.dumps(report["spool"], sort_keys=True))
    elif args.command == "import-gdelt-csv":
        if not args.input_csv:
            raise SystemExit("--input-csv is required")
        seen, inserted = import_gdelt_csv(spool, Path(args.input_csv))
        print(f"[NEWS][IMPORT] seen={seen} inserted={inserted}")


if __name__ == "__main__":
    main()
