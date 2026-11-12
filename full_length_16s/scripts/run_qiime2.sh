#!/usr/bin/env bash
# Requires an activated QIIME 2 2026.7 environment. Deliberately no 'set -e'.
MANIFEST="$1"
OUT="$2"
FRONT="$3"
CLASSIFIER="$4"
ADAPTER="$5"
if [ -z "$MANIFEST" ] || [ -z "$OUT" ]; then
  echo "Usage: bash run_qiime2.sh manifest.tsv output_dir verified_forward_primer [silva_classifier.qza] [reverse_primer_5to3]" >&2
  exit 2
fi
if [ -z "$FRONT" ] || [ "$FRONT" = "VERIFY_PRIMER" ]; then
  echo "BLOCK: Confirm the amplification forward primer. Do not guess it." >&2
  exit 2
fi
if ! command -v qiime >/dev/null 2>&1; then
  echo "BLOCK: Activate a QIIME 2 conda environment first." >&2
  exit 2
fi
if [ ! -f "$MANIFEST" ]; then echo "Missing manifest: $MANIFEST" >&2; exit 2; fi
mkdir -p "$OUT" || exit $?
run() {
  echo "RUN: $*"
  "$@"
  local code=$?
  if [ "$code" -ne 0 ]; then echo "FAILED ($code): $*" >&2; return "$code"; fi
}
if [ ! -f "$OUT/demux.qza" ]; then
  run qiime tools import --type 'SampleData[SequencesWithQuality]' \
    --input-path "$MANIFEST" --output-path "$OUT/demux.qza" \
    --input-format SingleEndFastqManifestPhred33V2 || exit $?
fi
if [ ! -f "$OUT/table.qza" ]; then
  if [ -n "$ADAPTER" ]; then
    run qiime dada2 denoise-ccs --i-demultiplexed-seqs "$OUT/demux.qza" \
      --p-front "$FRONT" --p-adapter "$ADAPTER" --p-max-ee 2 \
      --p-trunc-len 0 --p-min-len 1000 --p-max-len 1600 \
      --p-chimera-method consensus --p-min-fold-parent-over-abundance 3.5 \
      --p-n-threads 2 --o-table "$OUT/table.qza" \
      --o-representative-sequences "$OUT/rep-seqs.qza" \
      --o-denoising-stats "$OUT/stats.qza" || exit $?
  else
    run qiime dada2 denoise-ccs --i-demultiplexed-seqs "$OUT/demux.qza" \
      --p-front "$FRONT" --p-max-ee 2 \
      --p-trunc-len 0 --p-min-len 1000 --p-max-len 1600 \
      --p-chimera-method consensus --p-min-fold-parent-over-abundance 3.5 \
      --p-n-threads 2 --o-table "$OUT/table.qza" \
      --o-representative-sequences "$OUT/rep-seqs.qza" \
      --o-denoising-stats "$OUT/stats.qza" || exit $?
  fi
fi
mkdir -p "$OUT/table_export" "$OUT/stats_export" || exit $?
run qiime tools export --input-path "$OUT/table.qza" --output-path "$OUT/table_export" || exit $?
run biom convert -i "$OUT/table_export/feature-table.biom" -o "$OUT/feature-table.tsv" --to-tsv || exit $?
run qiime tools export --input-path "$OUT/stats.qza" --output-path "$OUT/stats_export" || exit $?
if [ -n "$CLASSIFIER" ]; then
  if [ ! -f "$CLASSIFIER" ]; then echo "Missing classifier: $CLASSIFIER" >&2; exit 2; fi
  if [ ! -f "$OUT/taxonomy.qza" ]; then
    run qiime feature-classifier classify-sklearn --i-classifier "$CLASSIFIER" \
      --i-reads "$OUT/rep-seqs.qza" --o-classification "$OUT/taxonomy.qza" \
      --p-n-jobs 2 || exit $?
  fi
  mkdir -p "$OUT/taxonomy_export" || exit $?
  run qiime tools export --input-path "$OUT/taxonomy.qza" \
    --output-path "$OUT/taxonomy_export" || exit $?
fi
echo "PASS: $OUT"
