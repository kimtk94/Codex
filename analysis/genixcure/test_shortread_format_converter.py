#!/usr/bin/env python3
"""Synthetic regression for the PacBio shortread-column converter; no private data."""
import csv
import gzip
import hashlib
import json
import tempfile
from pathlib import Path
from convert_pacbio_to_shortread_table import convert


def test():
    with tempfile.TemporaryDirectory() as td:
        base=Path(td)
        anc='AGCGATGACTAATACGTAGATGTACTGCCAA'
        data=[(anc+'ACGT',2,2),(anc+'AAGC',3,1)]
        source=base/'input.csv.gz'
        with gzip.open(source,'wt',newline='') as f:
            w=csv.writer(f)
            w.writerow(['sequence','count','full_span_count','other_mapped_count','length_bp','sequence_sha256'])
            for seq,cnt,full in data:
                w.writerow([seq,cnt,full,cnt-full,len(seq),hashlib.sha256(seq.encode()).hexdigest()])
        summary={
            'anchor_sequence':anc,
            'distinct_circular_normalized_sequences':2,
            'normalized_mapped_reads':5,
            'normalized_full_span_reads':3,
            'unresolved_mapped_reads':1,
            'all_unmapped_reads':1,
            'all_bam_reads':7,
            'count_table_sha256':'source-test',
        }
        r=convert(source,base/'output',summary,expected_source_size=None,progress_every=1)
        assert r['read_count_sum']==5 and r['unique_sequences']==2
        assert r['output_columns']==['sequence','read_count','length_bp']
        assert r['full_span_read_count_sum_original']==3
        assert len(r['output_md5'])==32 and len(r['output_sha256'])==64
        with gzip.open(base/'output'/r['output_file'],'rt',newline='') as f:
            table=list(csv.DictReader(f))
        assert len(table)==2 and sum(int(x['read_count']) for x in table)==5
        assert all(len(x['sequence'])==int(x['length_bp']) for x in table)
        # Counter-check: corrupt source read-count decomposition must never create a result.
        with gzip.open(source,'wt',newline='') as f:
            w=csv.writer(f);w.writerow(['sequence','count','full_span_count','other_mapped_count','length_bp','sequence_sha256'])
            for seq,cnt,full in data:
                w.writerow([seq,cnt,full,0,len(seq),hashlib.sha256(seq.encode()).hexdigest()])
        try:
            convert(source,base/'bad',summary,expected_source_size=None,progress_every=0)
            raise AssertionError('Expected to reject source count breakdown mismatch')
        except ValueError as e:
            assert 'full_span_count' in str(e)
    print('PASS: schema exact, count conservation, sequence/length/hash checks, failure case')

if __name__=='__main__':
    test()
