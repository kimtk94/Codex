from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


MARKET_MAP = {
    "US": "US",
    "KR": "KR",
    "BTC": "CRYPTO",
    "CRYPTO": "CRYPTO",
}
PIPELINE_VERSION = "market-tools-v2/model-shadow-v2_001"
PIPELINE_DB_STATUS = "ABORTED"
MODEL_NAME_PREFIX = "kalman_v2_logit"
CONFIRM_VALUE = "CONFIRM_NEON_SHADOW_MIRROR"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mirror Kalman V2 file SHADOW outputs into the existing Neon operational schema"
    )
    p.add_argument("--shadow-file", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--status-file", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() == "true"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def normalize_market(market: str) -> str:
    key = str(market or "").strip().upper()
    if key not in MARKET_MAP:
        raise ValueError(f"unsupported V2 market: {market!r}")
    return MARKET_MAP[key]


def validate_signal(signal: dict[str, Any]) -> None:
    payload = signal.get("payload") or {}
    errors: list[str] = []

    if not str(signal.get("run_id") or "").startswith("v2-"):
        errors.append("run_id must use v2- prefix")
    if str(signal.get("signal") or "").upper() != "SHADOW":
        errors.append("signal must be SHADOW")
    if signal.get("entry_allowed") is not False:
        errors.append("entry_allowed must be false")
    if str(signal.get("position_state") or "").upper() != "FLAT":
        errors.append("position_state must be FLAT")
    if _bool(payload.get("allow_trade_shadow")):
        errors.append("payload.allow_trade_shadow must be false")
    if _bool(payload.get("live_execution")):
        errors.append("payload.live_execution must be false")
    if _bool(payload.get("production_promotion")):
        errors.append("payload.production_promotion must be false")
    if not str(signal.get("strategy_version") or "").startswith("KALMAN_V2_"):
        errors.append("strategy_version must use KALMAN_V2_ prefix")

    normalize_market(str(signal.get("market") or ""))

    if errors:
        raise ValueError("; ".join(errors))


def validate_artifact(
    signal: dict[str, Any],
    artifact: dict[str, Any],
    artifact_sha256: str,
) -> None:
    payload = signal.get("payload") or {}
    errors: list[str] = []

    if str(artifact.get("strategy_version")) != str(signal.get("strategy_version")):
        errors.append("artifact strategy_version mismatch")
    if str(artifact.get("symbol")) != str(signal.get("symbol")):
        errors.append("artifact symbol mismatch")
    if str(artifact.get("model_version")) != str(payload.get("model_version")):
        errors.append("artifact model_version mismatch")
    if str(payload.get("model_sha256")) != artifact_sha256:
        errors.append("artifact SHA-256 mismatch")
    if artifact.get("shadow_only") is not True:
        errors.append("artifact.shadow_only must be true")
    if _bool(artifact.get("live_execution")):
        errors.append("artifact.live_execution must be false")
    if _bool(artifact.get("allow_trade_shadow")):
        errors.append("artifact.allow_trade_shadow must be false")

    if errors:
        raise ValueError("; ".join(errors))


def model_id_for(db_market: str, artifact: dict[str, Any]) -> str:
    version = str(artifact["model_version"]).replace(" ", "_")
    strategy = str(artifact["strategy_version"]).replace(" ", "_")
    return f"kalman-v2:{db_market.lower()}:{version}:{strategy}"


def model_name_for(original_market: str) -> str:
    return f"{MODEL_NAME_PREFIX}_{original_market.lower()}"


def parameter_hash(artifact: dict[str, Any]) -> str:
    return stable_hash(
        {
            "selected_features": artifact.get("selected_features"),
            "imputer_medians": artifact.get("imputer_medians"),
            "scaler_mean": artifact.get("scaler_mean"),
            "scaler_scale": artifact.get("scaler_scale"),
            "coefficients": artifact.get("coefficients"),
            "intercept": artifact.get("intercept"),
            "probability_threshold": artifact.get("probability_threshold"),
            "hyperparameters": artifact.get("hyperparameters"),
        }
    )


def build_record(
    signal: dict[str, Any],
    artifact: dict[str, Any],
    artifact_sha256: str,
) -> dict[str, Any]:
    validate_signal(signal)
    validate_artifact(signal, artifact, artifact_sha256)

    original_market = str(signal["market"]).upper()
    db_market = normalize_market(original_market)
    payload = dict(signal.get("payload") or {})
    now = datetime.now(timezone.utc).isoformat()

    stored_payload = {
        **payload,
        "allow_trade_shadow": False,
        "live_execution": False,
        "production_promotion": False,
        "neon_write": False,
        "neon_mirrored": True,
        "neon_mirrored_at": now,
        "source": "kalman-model-v2",
        "storage_mode": "NEON_SHADOW_MIRROR",
        "original_market": original_market,
        "dashboard_snapshot_created": False,
        "auto_trade_visible": False,
    }

    validation_metrics = {
        "validation_threshold_metrics": artifact.get("validation_threshold_metrics") or {},
        "test_metrics": artifact.get("test_metrics") or {},
        "candidate_summary": artifact.get("candidate_summary") or [],
    }

    return {
        "run_id": str(signal["run_id"]),
        "original_market": original_market,
        "db_market": db_market,
        "symbol": str(signal["symbol"]),
        "as_of": str(signal["as_of"]),
        "strategy_version": str(signal["strategy_version"]),
        "risk_gate": str(signal.get("risk_gate") or "SHADOW_ONLY"),
        "model_id": model_id_for(db_market, artifact),
        "model_name": model_name_for(original_market),
        "model_version": str(artifact["model_version"]),
        "feature_version": str(artifact.get("feature_set") or payload.get("feature_set") or ""),
        "artifact_sha256": artifact_sha256,
        "parameter_hash": parameter_hash(artifact),
        "validation_metrics": validation_metrics,
        "model_metadata": {
            "dataset_version": artifact.get("dataset_version"),
            "strategy_version": artifact.get("strategy_version"),
            "symbol": artifact.get("symbol"),
            "model_family": artifact.get("model_family"),
            "training_window": artifact.get("training_window"),
            "sklearn_version": artifact.get("sklearn_version"),
            "shadow_only": True,
            "live_execution": False,
            "allow_trade_shadow": False,
            "source": "kalman-model-v2-json",
        },
        "probability": float(payload["probability_up"]),
        "probability_threshold": float(payload["probability_threshold"]),
        "shadow_direction": str(payload.get("shadow_direction") or "WATCH"),
        "shadow_entry": bool(payload.get("shadow_entry_this_signal")),
        "signal_payload": stored_payload,
    }


def load_records(shadow_file: Path, model_dir: Path) -> list[dict[str, Any]]:
    signals = json.loads(shadow_file.read_text(encoding="utf-8"))
    if not isinstance(signals, list) or not signals:
        raise ValueError("shadow_signals.json must contain a non-empty list")

    records: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()

    for signal in signals:
        if not isinstance(signal, dict):
            raise ValueError("shadow signal entries must be JSON objects")
        original_market = str(signal.get("market") or "").upper()
        model_path = model_dir / original_market.lower() / "model.json"
        if not model_path.exists():
            raise FileNotFoundError(model_path)
        artifact = json.loads(model_path.read_text(encoding="utf-8"))
        artifact_sha = sha256_file(model_path)
        record = build_record(signal, artifact, artifact_sha)
        if record["run_id"] in seen_run_ids:
            raise ValueError(f"duplicate run_id in shadow file: {record['run_id']}")
        seen_run_ids.add(record["run_id"])
        records.append(record)

    return records


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def write_records(database_url: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is missing from the production Kalman environment") from exc

    run_ids = [r["run_id"] for r in records]
    now = datetime.now(timezone.utc)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT run_id FROM dashboard_snapshot WHERE run_id = ANY(%s)",
                (run_ids,),
            )
            dashboard_conflicts = [row[0] for row in cur.fetchall()]
            if dashboard_conflicts:
                raise RuntimeError(
                    "refusing V2 mirror because dashboard_snapshot already exists for: "
                    + ",".join(dashboard_conflicts)
                )

            cur.execute(
                """SELECT market, model_name, model_version, artifact_sha256
                   FROM model_registry
                   WHERE model_name = ANY(%s)""",
                ([r["model_name"] for r in records],),
            )
            existing = {
                (row[0], row[1], row[2]): row[3]
                for row in cur.fetchall()
            }
            for record in records:
                key = (
                    record["db_market"],
                    record["model_name"],
                    record["model_version"],
                )
                old_sha = existing.get(key)
                if old_sha and old_sha != record["artifact_sha256"]:
                    raise RuntimeError(
                        "model version already registered with a different artifact SHA: "
                        f"{key} existing={old_sha} new={record['artifact_sha256']}"
                    )

            cur.execute(
                """SELECT run_id, market, pipeline_version, model_version
                   FROM pipeline_run
                   WHERE run_id = ANY(%s)""",
                (run_ids,),
            )
            for run_id, market, pipeline_version, model_version in cur.fetchall():
                record = next(r for r in records if r["run_id"] == run_id)
                expected = (
                    record["db_market"],
                    PIPELINE_VERSION,
                    record["model_version"],
                )
                actual = (market, pipeline_version, model_version)
                if actual != expected:
                    raise RuntimeError(
                        f"run_id collision for {run_id}: existing={actual!r} expected={expected!r}"
                    )

            for record in records:
                cur.execute(
                    """INSERT INTO model_registry (
                           model_id, market, model_name, model_version, role,
                           feature_version, parameter_hash, artifact_sha256,
                           validation_metrics, metadata
                       ) VALUES (
                           %s,%s,%s,%s,'SHADOW',%s,%s,%s,%s::jsonb,%s::jsonb
                       )
                       ON CONFLICT (market, model_name, model_version) DO UPDATE SET
                           role='SHADOW',
                           feature_version=EXCLUDED.feature_version,
                           parameter_hash=EXCLUDED.parameter_hash,
                           artifact_sha256=EXCLUDED.artifact_sha256,
                           validation_metrics=EXCLUDED.validation_metrics,
                           metadata=EXCLUDED.metadata
                       RETURNING model_id""",
                    (
                        record["model_id"],
                        record["db_market"],
                        record["model_name"],
                        record["model_version"],
                        record["feature_version"],
                        record["parameter_hash"],
                        record["artifact_sha256"],
                        _json(record["validation_metrics"]),
                        _json(record["model_metadata"]),
                    ),
                )
                returned_model_id = cur.fetchone()[0]
                if returned_model_id != record["model_id"]:
                    record["model_id"] = returned_model_id

                run_metadata = {
                    "trade_enabled": False,
                    "shadow_only": True,
                    "source": "kalman-model-v2",
                    "storage_mode": "NEON_SHADOW_MIRROR",
                    "original_market": record["original_market"],
                    "strategy_version": record["strategy_version"],
                    "artifact_sha256": record["artifact_sha256"],
                    "dashboard_snapshot_created": False,
                    "auto_trade_visible": False,
                    "research_status": "SUCCESS",
                    "operational_commit": "ABORTED_SHADOW_ONLY",
                }
                cur.execute(
                    """INSERT INTO pipeline_run (
                           run_id, market, pipeline_version, data_as_of,
                           feature_version, model_version, git_sha,
                           started_at, completed_at, status, metadata
                       ) VALUES (
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
                       )
                       ON CONFLICT (run_id) DO UPDATE SET
                           data_as_of=EXCLUDED.data_as_of,
                           feature_version=EXCLUDED.feature_version,
                           model_version=EXCLUDED.model_version,
                           git_sha=EXCLUDED.git_sha,
                           completed_at=EXCLUDED.completed_at,
                           status=EXCLUDED.status,
                           error_message=NULL,
                           metadata=EXCLUDED.metadata""",
                    (
                        record["run_id"],
                        record["db_market"],
                        PIPELINE_VERSION,
                        record["as_of"],
                        record["feature_version"],
                        record["model_version"],
                        os.environ.get("KALMAN_GIT_SHA") or None,
                        now,
                        now,
                        PIPELINE_DB_STATUS,
                        _json(run_metadata),
                    ),
                )

                output_payload = {
                    "score_semantics": "PROBABILITY_UP",
                    "probability_threshold": record["probability_threshold"],
                    "shadow_direction": record["shadow_direction"],
                    "shadow_entry_this_signal": record["shadow_entry"],
                    "artifact_sha256": record["artifact_sha256"],
                    "strategy_version": record["strategy_version"],
                    "source": "kalman-model-v2",
                    "original_market": record["original_market"],
                }
                cur.execute(
                    """INSERT INTO model_output (
                           run_id, market, symbol, as_of, model_id, model_version,
                           score, probability, payload
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (run_id, market, symbol, model_version) DO UPDATE SET
                           as_of=EXCLUDED.as_of,
                           model_id=EXCLUDED.model_id,
                           score=EXCLUDED.score,
                           probability=EXCLUDED.probability,
                           payload=EXCLUDED.payload""",
                    (
                        record["run_id"],
                        record["db_market"],
                        record["symbol"],
                        record["as_of"],
                        record["model_id"],
                        record["model_version"],
                        record["probability"],
                        record["probability"],
                        _json(output_payload),
                    ),
                )

                reason_codes = [
                    "V2_RESEARCH_ONLY",
                    "NO_DASHBOARD_SNAPSHOT",
                    "AUTO_TRADE_ISOLATED",
                ]
                if record["risk_gate"] == "DATA_QUALITY_FAIL":
                    reason_codes.append("DATA_QUALITY_FAIL")

                cur.execute(
                    """INSERT INTO strategy_signal (
                           run_id, market, symbol, as_of, strategy_version,
                           signal, entry_allowed, risk_gate, position_state,
                           reason_codes, payload
                       ) VALUES (
                           %s,%s,%s,%s,%s,'SHADOW',false,%s,'FLAT',%s::jsonb,%s::jsonb
                       )
                       ON CONFLICT (run_id, market, symbol, strategy_version) DO UPDATE SET
                           as_of=EXCLUDED.as_of,
                           signal='SHADOW',
                           entry_allowed=false,
                           risk_gate=EXCLUDED.risk_gate,
                           position_state='FLAT',
                           target_price=NULL,
                           stop_price=NULL,
                           reason_codes=EXCLUDED.reason_codes,
                           payload=EXCLUDED.payload""",
                    (
                        record["run_id"],
                        record["db_market"],
                        record["symbol"],
                        record["as_of"],
                        record["strategy_version"],
                        record["risk_gate"],
                        _json(reason_codes),
                        _json(record["signal_payload"]),
                    ),
                )

        conn.commit()

    return {
        "status": "MIRRORED",
        "pipeline_version": PIPELINE_VERSION,
        "record_count": len(records),
        "run_ids": run_ids,
        "markets": [r["db_market"] for r in records],
        "model_ids": [r["model_id"] for r in records],
        "pipeline_db_status": PIPELINE_DB_STATUS,
        "latest_successful_run_eligible": False,
        "dashboard_snapshot_created": False,
        "strategy_ledger_written": False,
        "auto_trade_visible": False,
        "mirrored_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    args = parse_args()
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)

    shadow_file = Path(args.shadow_file).expanduser()
    model_dir = Path(args.model_dir).expanduser()
    status_file = Path(args.status_file).expanduser()

    try:
        records = load_records(shadow_file, model_dir)
        plan = {
            "status": "VALIDATED",
            "pipeline_version": PIPELINE_VERSION,
            "record_count": len(records),
            "run_ids": [r["run_id"] for r in records],
            "market_mapping": {
                r["original_market"]: r["db_market"] for r in records
            },
            "model_ids": [r["model_id"] for r in records],
            "pipeline_db_status": PIPELINE_DB_STATUS,
            "latest_successful_run_eligible": False,
            "dashboard_snapshot_created": False,
            "strategy_ledger_written": False,
            "auto_trade_visible": False,
        }

        if args.dry_run:
            plan["status"] = "DRY_RUN"
            atomic_json(status_file, plan)
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0

        enabled = os.environ.get("KALMAN_MODEL_V2_NEON_ENABLED", "false").lower() == "true"
        if not enabled:
            plan["status"] = "DISABLED"
            atomic_json(status_file, plan)
            print("MODEL_V2_NEON_SHADOW_MIRROR_DISABLED")
            return 0

        if os.environ.get("KALMAN_MODEL_V2_NEON_CONFIRM", "") != CONFIRM_VALUE:
            raise RuntimeError(
                "KALMAN_MODEL_V2_NEON_CONFIRM must equal "
                + CONFIRM_VALUE
            )

        database_url = os.environ.get("DATABASE_URL_WRITER", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL_WRITER is missing")

        result = write_records(database_url, records)
        atomic_json(status_file, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure = {
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "pipeline_db_status": PIPELINE_DB_STATUS,
            "latest_successful_run_eligible": False,
            "dashboard_snapshot_created": False,
            "strategy_ledger_written": False,
            "auto_trade_visible": False,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(status_file, failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
