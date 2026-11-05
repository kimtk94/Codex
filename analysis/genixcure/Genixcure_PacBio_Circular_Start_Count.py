#!/usr/bin/env python3
"""Reference-anchor circular rotation + exact abundance counting for all mapped PacBio BAM reads.

Designed for Genixcure EcoRV-linearized plasmid (6848 bp). The user-requested
circular-rotation equivalence is a *computational* normalization; it does NOT
assert that a sequenced molecule was physically circular or intact.

Input: original BAM + the 515 already completed full-run mapping chunks.
Output: checkpointed per-chunk normalized sequence rows; a final exact-count
CSV.gz (with full_span_count), top100 and conservation report. Never resamples.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import heapq
import json
import os
import shutil
import sqlite3
import tempfile
import zlib
from pathlib import Path

N_REF = 6848
ANCHOR_START0 = 3400  # reference EcoRV-linear 0-based; original circular plasmid 1-based 1269
ANCHOR_LEN = 31
FIELDS = ('sequence', 'count', 'full_span_count', 'length_bp')
REVCOMP = str.maketrans('ACGTN', 'TGCAN')


def rc(s):
    return s.translate(REVCOMP)[::-1]


def digest_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(2 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def reference_seq(path):
    s = ''.join(l.strip().upper() for l in Path(path).read_text().splitlines() if not l.startswith('>'))
    if len(s) != N_REF or set(s) - set('ACGTN'):
        raise ValueError('Require the 6848bp minimap2 EcoRV reference containing only ACGTN')
    a = s[ANCHOR_START0:ANCHOR_START0 + ANCHOR_LEN]
    if len(a) != ANCHOR_LEN or 'N' in a or s.count(a) != 1 or s.count(rc(a)):
        raise ValueError('Reference anchor is ambiguous or not unique')
    return s, a


def normalize(seq, strand, anchor):
    if strand not in ('+', '-'):
        return None, 'unrecognized_strand'
    if not seq:
        return None, 'empty_sequence'
    oriented = seq.upper() if strand == '+' else rc(seq.upper())
    start = oriented.find(anchor)
    if start < 0:
        return None, 'anchor_absent'
    if oriented.find(anchor, start + 1) >= 0:
        return None, 'anchor_ambiguous_multicopy'
    out = oriented[start:] + oriented[:start]
    if not out.startswith(anchor) or len(out) != len(seq):
        raise AssertionError('Circular normalization invariant violated')
    return out, 'normalized'


def atomic_copy(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(str(dst) + '.partial')
    shutil.copyfile(src, staged)
    if staged.stat().st_size != Path(src).stat().st_size:
        raise IOError('Incomplete Drive copy ' + str(dst))
    os.replace(staged, dst)


def load_mapping_chunks(mapping_dir):
    chunks = sorted(Path(mapping_dir).glob('chunk_*.done.json'))
    if not chunks:
        raise ValueError('No existing completed mapping checkpoint files')
    result = []
    last_end = None
    expected_params = None
    for i, f in enumerate(chunks):
        if f.name != f'chunk_{i:05d}.done.json':
            raise ValueError('Mapping chunks not continuous: ' + f.name)
        m = json.loads(f.read_text())
        if m['chunk_id'] != i or m['source_type'] != 'bam':
            raise ValueError('Mapping chunk identity invalid: ' + f.name)
        if expected_params is None:
            expected_params = m['params_sha256']
        if m['params_sha256'] != expected_params or (last_end is not None and last_end != m['start']):
            raise ValueError('Mapping chunk parameter/offset discontinuity: ' + f.name)
        path = f.with_name(f'chunk_{i:05d}.reads.csv.gz')
        if not path.is_file() or path.stat().st_size != m['read_csv_bytes']:
            raise ValueError('Missing or damaged per-read mapping file: ' + str(path))
        result.append((m, path))
        last_end = m['end']
    if result[-1][0].get('exhausted') is not True:
        raise RuntimeError('Full BAM mapping must reach EOF before normalization')
    return result, expected_params


def validate_existing(out, idx, manifest):
    dest = out / 'chunks' / f'chunk_{idx:05d}.normalized.csv.gz'
    done = out / 'chunks' / f'chunk_{idx:05d}.normalized.done.json'
    if not done.is_file():
        return None
    m = json.loads(done.read_text())
    if m['chunk_id'] != idx or m['params_sha256'] != manifest:
        raise ValueError('Normalization checkpoint parameter mismatch; use new OUT folder')
    if not dest.is_file() or dest.stat().st_size != m['csv_size'] or digest_file(dest) != m['csv_sha256']:
        raise ValueError('Corrupt normalization checkpoint: ' + str(done))
    return m


def run_normalize(args, anchor, manifest, chunks):
    try:
        import pysam
    except ImportError as e:
        raise RuntimeError('pysam is required to read the original BAM') from e
    if args.bam is None or not args.bam.is_file():
        raise FileNotFoundError('Original BAM unavailable; mapped per-read CSV does not contain bases')
    (args.out / 'chunks').mkdir(parents=True, exist_ok=True)
    summary = collections.Counter()
    done_count = 0
    with pysam.AlignmentFile(str(args.bam), 'rb', check_sq=False) as stream:
        for idx, (map_marker, map_path) in enumerate(chunks):
            prior = validate_existing(args.out, idx, manifest)
            if prior:
                summary.update(prior['metrics'])
                continue
            if args.max_chunks and done_count >= args.max_chunks:
                break
            stream.seek(int(map_marker['start']))
            c = collections.Counter()
            local = {}  # raw exact normalized sequence -> [count, full_span_count]
            unresolved_path = args.out / 'chunks' / f'chunk_{idx:05d}.unresolved.csv.gz'
            with tempfile.TemporaryDirectory(prefix='gxc_circular_') as temp:
                temp = Path(temp)
                uns = temp / 'unresolved.csv.gz'
                with gzip.open(map_path, 'rt', newline='') as fi, gzip.open(uns, 'wt', newline='', compresslevel=2) as unf:
                    reader = csv.DictReader(fi)
                    u = csv.writer(unf)
                    u.writerow(['ordinal', 'bam_qname', 'reason', 'mapped', 'strand', 'length_bp', 'full_span'])
                    for j, row in enumerate(reader):
                        try:
                            r = next(stream)
                        except StopIteration:
                            raise RuntimeError(f'BAM EOF mid-chunk {idx}')
                        ordinal = idx * args.mapping_chunk_reads + j + 1
                        seq = r.query_sequence or ''
                        if (int(row['ordinal']) != ordinal or r.query_name != row['bam_qname']
                                or len(seq) != int(row['length_bp']) or int(row['bam_flag']) != r.flag):
                            raise RuntimeError(f'BAM/mapping identity mismatch at chunk {idx}, ordinal {ordinal}')
                        c['input_reads'] += 1
                        is_mapped = row['mapped'] == '1'
                        full_span = row.get('full_span', '') == '1'
                        if not is_mapped:
                            c['unmapped_reads'] += 1
                            continue
                        c['mapped_reads'] += 1
                        rotated, status = normalize(seq, row['strand'], anchor)
                        if rotated is None:
                            c[status] += 1
                            u.writerow([ordinal, r.query_name, status, 1, row['strand'], len(seq), int(full_span)])
                            continue
                        c['normalized_reads'] += 1
                        if full_span:
                            c['normalized_full_span_reads'] += 1
                        if row['strand'] == '-':
                            c['reverse_complemented_reads'] += 1
                        if rotated in local:
                            local[rotated][0] += 1
                            local[rotated][1] += int(full_span)
                        else:
                            local[rotated] = [1, int(full_span)]
                if c['input_reads'] != map_marker['counts']['bam_records_or_unique_rows']:
                    raise RuntimeError('BAM count mismatch for chunk')
                if c['mapped_reads'] != map_marker['counts'].get('mapped_unique_or_records', 0):
                    raise RuntimeError('Mapped Read count differs from original mapping report')
                if int(stream.tell()) != map_marker['end']:
                    raise RuntimeError('BAM BGZF virtual-offset checkpoint differs from original mapping')
                f = temp / 'normalized.csv.gz'
                with gzip.open(f, 'wt', newline='', compresslevel=3) as outf:
                    writer = csv.writer(outf)
                    writer.writerow(FIELDS)
                    for seq, (count, full_count) in local.items():
                        writer.writerow([seq, count, full_count, len(seq)])
                target = args.out / 'chunks' / f'chunk_{idx:05d}.normalized.csv.gz'
                atomic_copy(f, target)
                if c['mapped_reads'] - c['normalized_reads']:
                    atomic_copy(uns, unresolved_path)
                marker = {
                    'chunk_id': idx, 'params_sha256': manifest,
                    'csv_name': target.name, 'csv_size': target.stat().st_size,
                    'csv_sha256': digest_file(target), 'metrics': dict(c),
                    'distinct_sequence_within_chunk': len(local),
                    'anchor_first_31bp': anchor,
                }
                mpath = temp / 'normalized.done.json'
                mpath.write_text(json.dumps(marker, indent=2))
                atomic_copy(mpath, args.out / 'chunks' / f'chunk_{idx:05d}.normalized.done.json')
            summary.update(c)
            done_count += 1
            print(f'[chunk {idx:05d}] mapped={c["mapped_reads"]}, normalized={c["normalized_reads"]}, full-span={c["normalized_full_span_reads"]}', flush=True)
    return summary


def run_aggregate(args, anchor, manifest, chunks):
    expected = len(chunks)
    summary = collections.Counter()
    normalized_files = []
    for i in range(expected):
        marker = validate_existing(args.out, i, manifest)
        if marker is None:
            raise RuntimeError(f'Normalized chunk {i} missing; rerun normalize stage')
        summary.update(marker['metrics'])
        normalized_files.append(args.out / 'chunks' / marker['csv_name'])
    if summary['input_reads'] != args.expected_reads or summary['normalized_reads'] + summary['unmapped_reads'] + sum(summary[k] for k in ('anchor_absent', 'anchor_ambiguous_multicopy', 'empty_sequence', 'unrecognized_strand')) != args.expected_reads:
        raise RuntimeError('Count conservation failed')
    scratch = args.scratch
    scratch.mkdir(parents=True, exist_ok=True)
    dbpath = scratch / 'circular_exact_count.sqlite3'
    if dbpath.exists():
        dbpath.unlink()  # Scratch database is disposable; source chunks are the checkpoints
    db = sqlite3.connect(dbpath)
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('PRAGMA synchronous=OFF')
    db.execute('PRAGMA cache_size=-200000')
    db.execute('CREATE TABLE grouped (hash BLOB PRIMARY KEY, seq_z BLOB NOT NULL, total INTEGER NOT NULL, full_count INTEGER NOT NULL, length_bp INTEGER NOT NULL)')
    query = ('INSERT INTO grouped (hash,seq_z,total,full_count,length_bp) VALUES (?,?,?,?,?) '
             'ON CONFLICT(hash) DO UPDATE SET total=total+excluded.total, full_count=full_count+excluded.full_count')
    for i, src in enumerate(normalized_files):
        with gzip.open(src, 'rt', newline='') as f:
            rows = csv.DictReader(f)
            if rows.fieldnames != list(FIELDS):
                raise RuntimeError('Normalized sequence schema changed')
            batch = []
            for r in rows:
                seq = r['sequence']
                if not seq.startswith(anchor) or len(seq) != int(r['length_bp']):
                    raise RuntimeError('Invalid normalized sequence in ' + src.name)
                batch.append((hashlib.sha256(seq.encode()).digest(), sqlite3.Binary(zlib.compress(seq.encode(), 2)), int(r['count']), int(r['full_span_count']), len(seq)))
                if len(batch) >= 1000:
                    db.executemany(query, batch)
                    batch.clear()
            if batch:
                db.executemany(query, batch)
        db.commit()
        if i % 25 == 0:
            print(f'[group] accumulated {i+1}/{expected} normalized chunks', flush=True)
    total, full, distinct = db.execute('SELECT SUM(total), SUM(full_count), COUNT(*) FROM grouped').fetchone()
    if total != summary['normalized_reads'] or full != summary['normalized_full_span_reads']:
        raise RuntimeError('Aggregated normalized count conservation failed')
    with tempfile.TemporaryDirectory(prefix='gxc_count_export_') as folder:
        folder = Path(folder)
        gz_path = folder / 'mapped_circular_start_normalized_count.csv.gz'
        top = []
        with gzip.open(gz_path, 'wt', newline='', compresslevel=3) as fh:
            writer = csv.writer(fh)
            writer.writerow(['sequence', 'count', 'full_span_count', 'other_mapped_count', 'length_bp', 'sequence_sha256'])
            for sha, seq_z, count, fullcount, length in db.execute('SELECT hash,seq_z,total,full_count,length_bp FROM grouped ORDER BY hash'):
                seq = zlib.decompress(seq_z).decode()
                if hashlib.sha256(seq.encode()).digest() != sha:
                    raise RuntimeError('Hash collision or corrupted sequence in scratch DB')
                writer.writerow([seq, count, fullcount, count - fullcount, length, sha.hex()])
                candidate = (count, fullcount, sha.hex(), length, seq)
                if len(top) < 100:
                    heapq.heappush(top, candidate)
                elif candidate > top[0]:
                    heapq.heapreplace(top, candidate)
        top_path = folder / 'top_100_mapped_circular_start_counts.csv'
        with top_path.open('w', newline='') as fh:
            writer = csv.writer(fh)
            writer.writerow(['sequence', 'count', 'full_span_count', 'length_bp', 'sequence_sha256'])
            for ct, fullct, digest, length, seq in sorted(top, reverse=True):
                writer.writerow([seq, ct, fullct, length, digest])
        atomic_copy(gz_path, args.out / gz_path.name)
        atomic_copy(top_path, args.out / top_path.name)
    report = {
        'status': 'CIRCULAR_START_NORMALIZED_COMPLETE',
        'note': 'Circular rotation is a computational representation, NOT evidence of physical circularity; source molecules were EcoRV-linearized.',
        'mapped_definition': 'mapped=1 in original per-BAM-record minimap2 mapping results',
        'anchor_reference_0based': ANCHOR_START0,
        'anchor_original_plasmid_1based': ((4716 + ANCHOR_START0) % N_REF) + 1,
        'anchor_sequence': anchor,
        'anchor_is_internal_reference_specific': True,
        'all_bam_reads': summary['input_reads'],
        'all_mapped_reads': summary['mapped_reads'],
        'all_unmapped_reads': summary['unmapped_reads'],
        'normalized_mapped_reads': total,
        'normalized_full_span_reads': full,
        'distinct_circular_normalized_sequences': distinct,
        'unresolved_mapped_reads': summary['mapped_reads'] - total,
        'breakdown': dict(summary),
        'count_table': 'mapped_circular_start_normalized_count.csv.gz',
        'count_table_sha256': digest_file(args.out / 'mapped_circular_start_normalized_count.csv.gz'),
        'processing_parameter_hash': manifest,
        'limitations': [
            'Read sequence is rotated to a shared internal 31bp reference anchor; it is not forced to start at the EcoRV physical cut.',
            'Missing or duplicated anchor reads are retained in separate unresolved CSVs and not silently merged.',
            'Exact sequence counting retains basecall errors, biological variants, and full/partial distinctions via full_span_count.',
            'UMI/barcode diversity is retained; no fuzzy clustering or edit-distance merging is performed.',
            'Splits/concatemers and physical termini are not evidence of intact single-copy plasmids.',
        ],
    }
    p = args.out / 'circular_start_normalized_summary.json'
    staged = args.scratch / 'summary.json'
    staged.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    atomic_copy(staged, p)
    db.close()
    print(json.dumps({k: report[k] for k in ('status', 'all_bam_reads', 'all_mapped_reads', 'normalized_mapped_reads', 'normalized_full_span_reads', 'distinct_circular_normalized_sequences', 'unresolved_mapped_reads')}, indent=2), flush=True)
    return report


def self_test():
    ref = 'CAGGGCACGGGCAGCTTGCCGGTGGTGCAGA' + 'T' * 75
    anchor = ref[:31]
    assert len(anchor) == 31
    original = ref + 'ATGCTAGC'
    a = original[40:] + original[:40]
    b = original[65:] + original[:65]
    c = rc(a)
    x = normalize(a, '+', anchor)[0]
    assert x == normalize(b, '+', anchor)[0] == normalize(c, '-', anchor)[0]
    assert x.startswith(anchor)
    assert normalize(original.replace(anchor, 'A' * 31), '+', anchor)[0] is None
    assert normalize(original + original, '+', anchor)[1] == 'anchor_ambiguous_multicopy'
    print('CIRCULAR ROTATION SELF TEST PASS')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bam', type=Path)
    p.add_argument('--reference', type=Path)
    p.add_argument('--mapping-chunks', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--scratch', type=Path, default=Path('/content/genixcure_circular_aggregation'))
    p.add_argument('--stage', choices=('normalize', 'aggregate', 'all'), default='all')
    p.add_argument('--mapping-chunk-reads', type=int, default=10000)
    p.add_argument('--max-chunks', type=int, default=0)
    p.add_argument('--expected-reads', type=int, default=5140518)
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args(argv)
    if a.self_test:
        self_test()
        return
    if not all((a.reference, a.mapping_chunks, a.out)):
        p.error('--reference, --mapping-chunks, --out required')
    if a.stage != 'aggregate' and not a.bam:
        p.error('--bam required for normalization stage')
    ref, anchor = reference_seq(a.reference)
    checkpoints, mapping_hash = load_mapping_chunks(a.mapping_chunks)
    a.out.mkdir(parents=True, exist_ok=True)
    parameters = {
        'version': 'genixcure_circular_start_exact_v1',
        'bam_size': a.bam.stat().st_size if a.bam else None,
        'reference_sha256': digest_file(a.reference),
        'original_mapping_params_hash': mapping_hash,
        'anchor_seq': anchor,
        'mapping_chunk_reads': a.mapping_chunk_reads,
    }
    # A BAM-less aggregate invocation uses the source identity previously recorded in OUT.
    manifest = a.out / 'normalization_parameters.json'
    if manifest.exists():
        before = json.loads(manifest.read_text())
        if a.stage == 'aggregate':
            parameters['bam_size'] = before['bam_size']
        if before != parameters:
            raise RuntimeError('Normalization parameter mismatch; use another OUT folder')
    else:
        if a.stage == 'aggregate':
            raise RuntimeError('Must run normalize stage first')
        manifest.write_text(json.dumps(parameters, indent=2))
    fpr = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    if a.stage in ('normalize', 'all'):
        run_normalize(a, anchor, fpr, checkpoints)
    if a.stage in ('aggregate', 'all'):
        run_aggregate(a, anchor, fpr, checkpoints)


if __name__ == '__main__':
    main()
