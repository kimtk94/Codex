#!/usr/bin/env python3
"""PacBio HiFi EcoRV-linear plasmid: CIGAR-based read-only alignment diagnostic.

No biological variants or UMI families are called.  Coordinates are zero-based,
half-open along the 6,848-bp EcoRV-linearized reference.
"""
import argparse
import csv
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

ITR_WINDOW = (2110, 2280)      # SnapGene ITR 1..123 -> linear reference 2132..2255 (0-based)
BARCODE_WINDOW = (2360, 2530)  # SnapGene UMI/Barcode tags near linear ref 2437..2447
CIGAR_RE = re.compile(r'(\d+)([MIDNSHP=X])')


def cigar_ops(cigar):
    result = [(int(n), op) for n, op in CIGAR_RE.findall(cigar)]
    if not result or ''.join(str(n) + op for n, op in result) != cigar:
        raise ValueError(f'Invalid CIGAR {cigar[:80]}')
    return result


def ref_overlap(pos, length, window):
    return max(0, min(pos + length, window[1]) - max(pos, window[0]))


def summarize_cigar(tstart, cigar, itr=ITR_WINDOW, barcode=BARCODE_WINDOW):
    pos = tstart
    obs = dict(itr_D=0, itr_I=0, barcode_D=0, barcode_I=0, large_D=0, large_I=0,
               cigar_X=0, cigar_EQ=0)
    for n, op in cigar_ops(cigar):
        if op == 'I':
            if itr[0] <= pos < itr[1]: obs['itr_I'] += n
            if barcode[0] <= pos < barcode[1]: obs['barcode_I'] += n
            if n >= 8: obs['large_I'] += 1
        elif op in ('D', 'N'):
            obs['itr_D'] += ref_overlap(pos, n, itr)
            obs['barcode_D'] += ref_overlap(pos, n, barcode)
            if n >= 30: obs['large_D'] += 1
            pos += n
        elif op in ('M', '=', 'X'):
            if op == '=': obs['cigar_EQ'] += n
            elif op == 'X': obs['cigar_X'] += n
            pos += n
        elif op in ('S', 'H', 'P'):
            pass
    obs['itr_net_ref_gap'] = obs['itr_D'] - obs['itr_I']
    obs['barcode_net_query_extra'] = obs['barcode_I'] - obs['barcode_D']
    return obs


def fasta_stats(path):
    # Exact count only: streaming, no read-length assumptions.
    n = 0
    with path.open() as fh:
        for line in fh:
            if line.startswith('>'): n += 1
    return n


def metadata_read(path):
    data = {}
    with path.open(newline='') as f:
        for row in csv.DictReader(f):
            key = row['query_id']
            if key in data: raise ValueError(f'Duplicate query_id: {key}')
            data[key] = {'read_count': int(row['read_count']), 'length_bp': int(row['length_bp'])}
    if any(x['read_count'] <= 0 for x in data.values()):
        raise ValueError('Read counts must be positive')
    return data


def run_minimap2(reference, fasta, paf, threads):
    exe = shutil.which('minimap2')
    if not exe: raise RuntimeError('minimap2 is missing; install it in this Colab runtime')
    cmd = [exe, '-x', 'map-hifi', '--secondary=no', '--eqx', '-c', '-t', str(threads),
           str(reference), str(fasta)]
    log = paf.with_suffix('.minimap2.log')
    with paf.open('w') as f, log.open('w') as e:
        process = subprocess.run(cmd, stdout=f, stderr=e, check=False)
    if process.returncode:
        print(log.read_text(errors='replace')[-8000:])
        raise RuntimeError(f'minimap2 exit code {process.returncode}')
    if paf.stat().st_size == 0:
        raise RuntimeError('PAF was empty: inspect minimap2 log')
    return cmd


def load_paf(paf, metadata, ref_length):
    mapped = {}
    total_segments = Counter()
    nmissing_cigar = 0
    with paf.open() as f:
        for line in f:
            v = line.rstrip('\n').split('\t')
            if len(v) < 12: continue
            q = v[0]
            if q not in metadata: continue
            if any(tag == 'tp:A:S' for tag in v[12:]): continue
            total_segments[q] += 1
            qlen, qs, qe = [int(v[i]) for i in (1, 2, 3)]
            tlen, ts, te = [int(v[i]) for i in (6, 7, 8)]
            nm, blen, mq = [int(v[i]) for i in (9, 10, 11)]
            if tlen != ref_length: raise ValueError(f'Target length mismatch: {tlen} != {ref_length}')
            if qlen != metadata[q]['length_bp']: raise ValueError(f'Query length mismatch: {q}')
            cg = next((tag[5:] for tag in v[12:] if tag.startswith('cg:Z:')), '')
            if not cg: nmissing_cigar += 1
            score = (qe - qs, nm, mq)
            obs = summarize_cigar(ts, cg) if cg else {}
            candidate = {'query_id': q, 'read_count': metadata[q]['read_count'],
                         'length_bp': qlen, 'strand': v[4], 'qcov': (qe - qs) / qlen,
                         'rcov': (te - ts) / ref_length, 'identity': nm / blen if blen else 0,
                         'ref_start': ts, 'ref_end': te, 'mapq': mq,
                         'span_full_length': bool(0.8 * ref_length <= qlen <= 1.25 * ref_length
                            and (qe - qs) / qlen >= .90 and (te - ts) / ref_length >= .90
                            and ts <= 150 and ref_length - te <= 150),
                         **obs}
            if q not in mapped or score > mapped[q][0]: mapped[q] = (score, candidate)
    if nmissing_cigar:
        raise RuntimeError(f'{nmissing_cigar} PAF segments lacked cg:Z CIGAR; rerun minimap2 with -c')
    return {q:item[1] for q,item in mapped.items()}, total_segments


def execute(reference, fasta, metadata_path, output, threads=4, refresh=False):
    output.mkdir(parents=True, exist_ok=True)
    refseq = ''.join(x.strip() for x in reference.read_text().splitlines() if not x.startswith('>'))
    if len(refseq) != 6848: raise ValueError(f'Unexpected reference length: {len(refseq)}')
    metadata = metadata_read(metadata_path)
    n_fasta = fasta_stats(fasta)
    if n_fasta != len(metadata): raise ValueError(f'FASTA IDs {n_fasta} != metadata {len(metadata)}')
    paf = output/'pilot_EcoRV_linear_eqx_cigar.paf'
    if refresh or not paf.is_file() or not paf.stat().st_size:
        run_minimap2(reference, fasta, paf, threads)
    aligned, segments = load_paf(paf, metadata, len(refseq))
    columns = ['query_id', 'read_count', 'length_bp', 'strand', 'qcov', 'rcov', 'identity',
               'ref_start', 'ref_end', 'mapq', 'span_full_length', 'itr_D', 'itr_I',
               'itr_net_ref_gap', 'barcode_D', 'barcode_I', 'barcode_net_query_extra',
               'large_D', 'large_I', 'cigar_X', 'cigar_EQ', 'primary_or_split_segments']
    out_csv = output/'pilot_CIGAR_structural_audit.csv'
    classifications = Counter()
    weighted = Counter()
    events = Counter()
    weighted_events = Counter()
    with out_csv.open('w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=columns)
        wr.writeheader()
        for q, meta in metadata.items():
            x = aligned.get(q)
            if x is None:
                classifications['unmapped'] += 1
                weighted['unmapped'] += meta['read_count']
                continue
            row = {k: x.get(k, '') for k in columns}
            row['primary_or_split_segments'] = segments[q]
            wr.writerow(row)
            k = 'full_span' if x['span_full_length'] else 'not_full_span'
            classifications[k] += 1
            weighted[k] += meta['read_count']
            conditions = {
                'ITR_net_gap_90_102': 90 <= x['itr_net_ref_gap'] <= 102,
                'Barcode_net_extra_10_14': 10 <= x['barcode_net_query_extra'] <= 14,
                'Barcode_net_extra_22_26': 22 <= x['barcode_net_query_extra'] <= 26,
                'multi_primary_or_split': segments[q] > 1,
            }
            for flag, match in conditions.items():
                if match:
                    events[flag] += 1
                    weighted_events[flag] += meta['read_count']
    result = {
        'status': 'CIGAR_PILOT_COMPLETED', 'reference_length_bp': len(refseq),
        'pilot_unique_total': len(metadata), 'pilot_weighted_reads': sum(m['read_count'] for m in metadata.values()),
        'mapped_unique': len(aligned), 'coverage_class_unique': dict(classifications),
        'coverage_class_weighted': dict(weighted), 'structural_events_unique': dict(events),
        'structural_events_weighted': dict(weighted_events),
        'reference_ITR_region_linear_0based_half_open': ITR_WINDOW,
        'reference_Barcode_UMI_region_linear_0based_half_open': BARCODE_WINDOW,
        'important_warning': 'Exploratory candidate structural events only; repeated ITR mapping may be ambiguous. Neither pilot unique sampling nor weighted pilot_read_count is a population read fraction. Validate UMI and deletion boundaries via raw BAM before biological claims.'
    }
    assert sum(classifications.values()) == len(metadata)
    result_path = output/'pilot_CIGAR_structural_summary.json'
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def self_test():
    assert cigar_ops('20=96D50=12I30X') == [(20, '='), (96, 'D'), (50, '='), (12, 'I'), (30, 'X')]
    a = summarize_cigar(2110, '20=96D170=12I30=', itr=(2110,2300), barcode=(2390,2500))
    assert a['itr_D'] == 96 and a['itr_net_ref_gap'] == 96, a
    assert a['barcode_I'] == 12 and a['barcode_net_query_extra'] == 12, a
    assert a['large_D'] == 1 and a['large_I'] == 1
    assert ref_overlap(5, 10, (8, 12)) == 4
    try:
        cigar_ops('20=garbage')
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid CIGAR incorrectly accepted')
    print('GENIXCURE ECORV CIGAR SELF TEST PASS')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--reference', type=Path)
    ap.add_argument('--fasta', type=Path)
    ap.add_argument('--metadata', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        self_test(); return
    if not all((a.reference, a.fasta, a.metadata, a.output)):
        ap.error('--reference, --fasta, --metadata, --output are required')
    execute(a.reference, a.fasta, a.metadata, a.output, a.threads, a.refresh)


if __name__ == '__main__':
    main()
