#!/usr/bin/env python3
"""Stream the completed Genixcure PacBio circular-normalized table into a three-column CSV.gz export.

The three output columns are exactly the requested three-column sequence/count/length schema:
    sequence,read_count,length_bp

Only exact, anchor-normalized sequences are included. No re-alignment, UMI collapse,
quality correction, fuzzy clustering, or mutation of the source table is performed.
The unmodified source remains the authoritative six-column QC table.
"""
import argparse
import csv
import gzip
import hashlib
import heapq
import json
import os
from pathlib import Path
import sys
import time

EXPECTED_FIELDS = {'sequence', 'count', 'full_span_count', 'other_mapped_count', 'length_bp', 'sequence_sha256'}
OUT_COLUMNS = ['sequence', 'read_count', 'length_bp']


def file_hashes(path):
    h = hashlib.sha256()
    m = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
            m.update(chunk)
    return h.hexdigest(), m.hexdigest()


def convert(source, output_folder, summary, expected_source_size=None, progress_every=100000):
    source = Path(source)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise FileNotFoundError(source)
    if expected_source_size is not None and source.stat().st_size != expected_source_size:
        raise RuntimeError('Source file size differs from established final Drive file')
    anchor = summary['anchor_sequence']
    sample = 'PLA_6_13'
    out_name = f'{sample}_PacBio_Circular_Normalized_Unique_Sequences.csv.gz'
    dst = output_folder / out_name
    stage = output_folder / (out_name + '.partial')
    if stage.exists():
        stage.unlink()
    start = time.monotonic()
    rows = total_count = full_sum = other_sum = 0
    top = []
    csv.field_size_limit(sys.maxsize)
    try:
        with gzip.open(source, 'rt', newline='', encoding='utf-8') as inf, gzip.open(stage, 'wt', newline='', encoding='utf-8', compresslevel=3) as outf:
            reader = csv.DictReader(inf)
            if set(reader.fieldnames or []) != EXPECTED_FIELDS:
                raise ValueError(f'Source table has unexpected columns: {reader.fieldnames}')
            writer = csv.writer(outf)
            writer.writerow(OUT_COLUMNS)
            for r in reader:
                seq = r['sequence']
                cnt = int(r['count'])
                length = int(r['length_bp'])
                full = int(r['full_span_count'])
                other = int(r['other_mapped_count'])
                if cnt < 1 or not seq.startswith(anchor) or len(seq) != length:
                    raise ValueError(f'Invalid sequence/count/length in row {rows+1}')
                if full < 0 or other < 0 or full + other != cnt:
                    raise ValueError(f'Bad full_span_count decomposition in row {rows+1}')
                # Verify sequence identity from the source, not a truncated prefix.
                if hashlib.sha256(seq.encode()).hexdigest() != r['sequence_sha256']:
                    raise ValueError(f'Source SHA256 mismatch in row {rows+1}')
                writer.writerow((seq, cnt, length))
                rows += 1
                total_count += cnt
                full_sum += full
                other_sum += other
                rank = (cnt, seq)
                if len(top) < 100:
                    heapq.heappush(top, rank)
                elif rank > top[0]:
                    heapq.heapreplace(top, rank)
                if progress_every and rows % progress_every == 0:
                    pct = 100 * rows / summary['distinct_circular_normalized_sequences']
                    print(f'[CONVERT] {rows:,}/{summary["distinct_circular_normalized_sequences"]:,} ({pct:.2f}%) '
                          f'count_sum={total_count:,} elapsed={(time.monotonic()-start)/60:.1f} min', flush=True)
        expected = {
            'unique_sequences': summary['distinct_circular_normalized_sequences'],
            'normalized_reads': summary['normalized_mapped_reads'],
            'normalized_full_span_reads': summary['normalized_full_span_reads'],
        }
        actual = {'unique_sequences': rows, 'normalized_reads': total_count, 'normalized_full_span_reads': full_sum}
        if actual != expected or total_count != full_sum + other_sum:
            raise RuntimeError(f'Full count conservation FAILED: actual={actual} expected={expected}')
        os.replace(stage, dst)
    except Exception:
        # Keep .partial for diagnosis; no incomplete file is advertised as complete.
        raise
    top_path = output_folder / f'{sample}_PacBio_Circular_Normalized_Top100.csv'
    with top_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(OUT_COLUMNS)
        for cnt, seq in sorted(top, key=lambda z: (-z[0], z[1])):
            writer.writerow((seq, cnt, len(seq)))
    sha, md5 = file_hashes(dst)
    result = {
        'status': 'PASS', 'sample': sample, 'source_file': source.name,
        'source_file_bytes': source.stat().st_size,
        'output_file': out_name, 'output_file_bytes': dst.stat().st_size,
        'output_columns': OUT_COLUMNS, 'output_sha256': sha, 'output_md5': md5,
        'unique_sequences': rows,
        'read_count_sum': total_count,
        'full_span_read_count_sum_original': full_sum,
        'other_mapped_read_count_sum_original': other_sum,
        'unresolved_mapped_reads_excluded': summary['unresolved_mapped_reads'],
        'unmapped_reads_excluded': summary['all_unmapped_reads'],
        'original_total_reads': summary['all_bam_reads'],
        'source_summary_sha256': summary['count_table_sha256'],
        'note': 'Exact sequences after shared circular anchor/direction normalization. Computational rotation only; no error correction or similarity clustering.',
        'runtime_seconds': round(time.monotonic() - start, 2)
    }
    (output_folder / f'{sample}_PacBio_Circular_Normalized_Validation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('[PASS]',json.dumps({k:result[k] for k in ('unique_sequences','read_count_sum','output_file_bytes','output_sha256')}, indent=2),flush=True)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--summary', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    p.add_argument('--expected-source-bytes', type=int, default=8402255312)
    p.add_argument('--progress-every', type=int, default=100000)
    a = p.parse_args(argv)
    data = json.loads(a.summary.read_text(encoding='utf-8'))
    assert data['status'] == 'CIRCULAR_START_NORMALIZED_COMPLETE'
    convert(a.source, a.output_dir, data, a.expected_source_bytes, a.progress_every)

if __name__ == '__main__':
    main()
