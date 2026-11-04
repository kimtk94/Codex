#!/usr/bin/env python3
"""Turn a single-cut circular SnapGene plasmid into an EcoRV-linear reference.

Requires Biopython. Keeps all ambiguous IUPAC codes in the archival FASTA,
uses N at ambiguous positions in the minimap2 mapping FASTA.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from Bio import SeqIO
from Bio.Restriction import EcoRV


def digest(record):
    seq = str(record.seq).upper()
    if record.annotations.get('topology', '').lower() != 'circular':
        raise ValueError('SnapGene record topology is not circular; cannot infer a single EcoRV linearization')
    sites = list(EcoRV.search(record.seq, linear=False))
    if len(sites) != 1:
        raise ValueError(f'Expected exactly ONE EcoRV cleavage site: found {len(sites)} at {sites}')
    cut_1based = int(sites[0])  # 1-based base *after* cut
    cut_0based = cut_1based - 1
    motif = (seq + seq)[cut_0based-3:cut_0based+3]
    if motif != 'GATATC':
        raise AssertionError(f'EcoRV site mismatch at expected cut {cut_1based}: {motif}')
    linear = seq[cut_0based:] + seq[:cut_0based]
    assert len(linear) == len(seq)
    assert linear[-3:] + linear[:3] == 'GATATC'
    annotations = []
    for feat in record.features:
        labels = feat.qualifiers.get('label') or []
        label = labels[0] if isinstance(labels, list) else str(labels)
        if label:
            annotations.append({'label': label, 'type': feat.type,
                                'start_1based': int(feat.location.start) + 1,
                                'end_1based_inclusive': int(feat.location.end),
                                'strand': feat.location.strand})
    return linear, {
        'source_topology': record.annotations.get('topology'),
        'plasmid_length_bp': len(seq),
        'ecorv_site_count': len(sites),
        'ecorv_recognition': 'GATATC',
        'ecorv_recognition_first_base_1based': cut_1based-3,
        'ecorv_recognition_last_base_1based': cut_1based+2,
        'ecorv_cut_between_original_bases_1based': [cut_1based-1, cut_1based],
        'linear_reference_original_first_base_1based': cut_1based,
        'linear_reference_original_last_base_1based': cut_1based-1,
        'iupac_ambiguous_bases': dict(collections.Counter(x for x in seq if x not in 'ACGT')),
        'iupac_ambiguous_positions_original_1based': [i+1 for i,ch in enumerate(seq) if ch not in 'ACGT'],
        'feature_annotations': annotations,
        'important_warning': 'UMI/Barcode feature LABELS are present but do not establish actual read-variable region lengths; do not remove or group these before alignment.'
    }


def write_fasta(path, name, seq):
    with Path(path).open('w') as out:
        out.write(f'>{name}\n')
        for i in range(0, len(seq), 80):
            out.write(seq[i:i+80] + '\n')


def create(source, output):
    source = Path(source)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    record = SeqIO.read(str(source), 'snapgene')
    seq = str(record.seq).upper()
    linear, meta = digest(record)
    meta['snapgene_source_filename'] = source.name
    meta['snapgene_source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    meta['reference_linear_sha256'] = hashlib.sha256(linear.encode()).hexdigest()
    meta['mapped_reference_ambiguous_to_N'] = True
    write_fasta(output/'plasmid_original_circular_IUPAC.fasta', 'Genixcure_original_circular_6848bp', seq)
    write_fasta(output/'plasmid_EcoRV_linear_IUPAC.fasta', 'Genixcure_EcoRV_linear_6848bp_IUPAC', linear)
    write_fasta(output/'plasmid_EcoRV_linear_minimap2.fasta', 'Genixcure_EcoRV_linear_6848bp',
                ''.join(b if b in 'ACGT' else 'N' for b in linear))
    (output/'EcoRV_reference_manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return meta


def self_test():
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord
    # One EcoRV site, distinct flanks, reversible rotation, and blunt-end junction.
    record = SeqRecord(Seq('AACCGATATCTTGGCCAA'))
    record.annotations['topology'] = 'circular'
    linear, m = digest(record)
    assert len(linear) == 18
    assert m['ecorv_site_count'] == 1
    assert m['ecorv_cut_between_original_bases_1based'] == [7, 8]
    assert linear == 'ATCTTGGCCAAAACCGAT'
    assert linear[-3:] + linear[:3] == 'GATATC'
    print('EcoRV circular→linear reference self-test PASS')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        if not a.source or not a.out:
            ap.error('--source and --out required unless --self-test')
        m = create(a.source, a.out)
        print(json.dumps({k:v for k,v in m.items() if k not in ('feature_annotations','important_warning')}, indent=2))

if __name__ == '__main__':
    main()
