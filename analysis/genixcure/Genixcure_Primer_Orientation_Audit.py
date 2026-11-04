#!/usr/bin/env python3
"""Read-only exact reverse-complement audit for Genixcure single_end count CSVs.

This is NOT a variant caller, primer trimmer, quality filter or deduplicator of
independent DNA molecules. It only combines an exact sequence with its exact RC.
"""
import argparse
import csv
import gzip
import json
import tempfile
from collections import Counter
from pathlib import Path

TRANSLATION = str.maketrans('ACGT', 'TGCA')
A = 'CGCGATATATCGTGTACAAG'
B = 'ACCTTCCATCGATAAGGAAG'
DEFAULT_SAMPLES = ['Brain_1', 'Brain_2', 'Brain_3', 'Motor_1', 'Motor_2', 'Motor_3',
                   'SH_SY5Y_1', 'SH_SY5Y_2', 'SH_SY5Y_3', 'Input']


def reverse_complement(seq):
    return seq.translate(TRANSLATION)[::-1]


def audit_file(sample, filename):
    canonical = {}
    endpairs = Counter()
    hits = Counter()
    original_unique = original_reads = original_singletons = 0
    with gzip.open(filename, 'rt', newline='') as f:
        rd = csv.DictReader(f)
        if rd.fieldnames != ['sequence', 'read_count', 'length_bp']:
            raise ValueError(f'{filename}: unexpected header {rd.fieldnames}')
        for row in rd:
            seq = row['sequence'].upper()
            n = int(row['read_count'])
            if not seq or len(seq) != int(row['length_bp']) or n <= 0 or set(seq) - set('ACGTN'):
                raise ValueError(f'{filename}: invalid sequence/count/length')
            original_unique += 1
            original_reads += n
            original_singletons += (n == 1)
            rc = reverse_complement(seq)
            key = min(seq, rc)
            canonical[key] = canonical.get(key, 0) + n
            hits['A_to_rcB'] += n * (seq.startswith(A) and seq.endswith(reverse_complement(B)))
            hits['B_to_rcA'] += n * (seq.startswith(B) and seq.endswith(reverse_complement(A)))
            hits['A_to_rcA'] += n * (seq.startswith(A) and seq.endswith(reverse_complement(A)))
            hits['B_to_rcB'] += n * (seq.startswith(B) and seq.endswith(reverse_complement(B)))
            endpairs[(seq[:20], seq[-20:])] += n
    if original_reads != sum(canonical.values()):
        raise AssertionError('Read count conservation failed')
    canonical_unique = len(canonical)
    pair_count = hits['A_to_rcB'] + hits['B_to_rcA']
    dominant, count = endpairs.most_common(1)[0] if endpairs else (('', ''), 0)
    return {'sample': sample, 'single_end_reads': original_reads,
            'single_end_original_unique': original_unique,
            'single_end_original_singletons': original_singletons,
            'single_end_rc_canonical_unique': canonical_unique,
            'single_end_rc_canonical_singletons': sum(v == 1 for v in canonical.values()),
            'unique_reduction_n': original_unique - canonical_unique,
            'unique_reduction_pct': round(100 * (original_unique - canonical_unique) / original_unique, 3)
                                    if original_unique else 0,
            **hits,
            'pair_A_B_fraction_pct': round(100 * pair_count / original_reads, 3)
                                     if original_reads else 0,
            'top_pair': ' / '.join(dominant), 'top_pair_reads': count}


def run(input_dir, output, samples, skip_missing=True):
    results = []
    missing = []
    for sample in samples:
        path = input_dir / sample / f'{sample}_single_end_unique.csv.gz'
        if not path.is_file():
            missing.append(sample)
            if not skip_missing:
                raise FileNotFoundError(path)
            print(f'[{sample}] NOT COMPLETE (no CSV)', flush=True)
            continue
        row = audit_file(sample, path)
        results.append(row)
        print(f"[{sample}] unique {row['single_end_original_unique']:,} -> "
              f"{row['single_end_rc_canonical_unique']:,}; "
              f"RC reduction {row['unique_reduction_pct']:.1f}%; "
              f"paired motif reads {row['pair_A_B_fraction_pct']:.1f}%", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = {'audit_kind': 'exact_RC_canonicalization_within_single_end_only',
            'primer_flank_motif_A': A, 'primer_flank_motif_B': B,
            'interpretation_note': 'Exploratory only. No molecular deduplication or validation of primers.',
            'results': results, 'not_complete': missing}
    temp = output.with_name(output.name + '.partial')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temp.replace(output)
    print(f'Wrote {output}; samples audited={len(results)}; missing={len(missing)}')
    return data


def self_test():
    with tempfile.TemporaryDirectory() as d:
        directory = Path(d)
        folder = directory / 'TEST'
        folder.mkdir()
        s1 = A + 'ACGTACGT' + reverse_complement(B)
        s2 = reverse_complement(s1)
        s3 = 'ACGTCGCG'
        with gzip.open(folder / 'TEST_single_end_unique.csv.gz', 'wt') as f:
            f.write('sequence,read_count,length_bp\n')
            for s, n in [(s1, 4), (s2, 3), (s3, 2)]:
                f.write(f'{s},{n},{len(s)}\n')
        obj = run(directory, directory / 'out.json', ['TEST'], skip_missing=False)
        item = obj['results'][0]
        assert item['single_end_original_unique'] == 3
        assert item['single_end_rc_canonical_unique'] == 2
        assert item['single_end_reads'] == 9
        assert item['A_to_rcB'] + item['B_to_rcA'] == 7
        assert (directory / 'out.json').exists()
    print('SELF TEST PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path,
                        default=Path('/content/drive/MyDrive/Genixcure_PCR_Merge_Analysis/PCR_11_Reanalysis_QC_v2'))
    parser.add_argument('--output', type=Path,
                        default=Path('/content/drive/MyDrive/Genixcure_PCR_Merge_Analysis/PCR_11_Reanalysis_QC_v2/Primer_Diagnostic_v1/primer_orientation_audit.json'))
    parser.add_argument('--samples', nargs='+', default=DEFAULT_SAMPLES)
    parser.add_argument('--fail-on-missing', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    run(args.input_dir, args.output, args.samples, skip_missing=not args.fail_on_missing)


if __name__ == '__main__':
    main()
