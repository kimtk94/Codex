#!/usr/bin/env bash

TAG="${KALMAN_PM_ARCHIVE_TAG:-data-2026-09-13}"
REPO="${KALMAN_PM_ARCHIVE_REPO:-DineshKumar8399/polymarket-orderbook-dataset}"
ASSET="${KALMAN_PM_ARCHIVE_ASSET:-polymarket-orderbook-2026-09-13.tar.zst}"
EXPECTED_SHA256="${KALMAN_PM_ARCHIVE_SHA256:-13c76e8868589a46a60cd1b6eda80c2094fc36b32f51fc6435fa4ba9c6fb8086}"
DEST="${KALMAN_PM_ARCHIVE_DIR:-/home/taehoon/kalman-data/prediction-market/archive-2026-09-13}"

mkdir -p "$DEST" || exit 10
cd "$DEST" || exit 11

if [ ! -f "$ASSET" ]; then
  gh release download "$TAG" \
    --repo "$REPO" \
    --pattern "$ASSET" || exit 20
fi

ACTUAL_SHA256="$(sha256sum "$ASSET" | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "[FAIL] archive sha256 mismatch" >&2
  echo "expected=$EXPECTED_SHA256" >&2
  echo "actual=$ACTUAL_SHA256" >&2
  exit 21
fi

echo "[PASS] archive sha256=$ACTUAL_SHA256"

if [ ! -f markets.parquet ]; then
  tar --zstd -xf "$ASSET" || exit 30
fi

for required in markets.parquet data_quality.parquet watch_quotes.parquet; do
  if [ ! -f "$required" ]; then
    echo "[FAIL] missing extracted file: $required" >&2
    exit 31
  fi
done

if [ ! -d quotes ]; then
  echo "[FAIL] missing quotes directory" >&2
  exit 32
fi

echo "[READY] $DEST"
