#!/usr/bin/env python3
"""Synthetic all-chunk count conservation and circular rotation regression test.
No raw plasmid or private PacBio data required.
"""
import csv
import gzip
import importlib.util
import json
import random
import sys
import tempfile
import types
from pathlib import Path

SCRIPT = Path(__file__).with_name('Genixcure_PacBio_Circular_Start_Count.py')
spec = importlib.util.spec_from_file_location('gxc', SCRIPT)
gxc = importlib.util.module_from_spec(spec)
sys.modules['gxc'] = gxc
spec.loader.exec_module(gxc)


def test():
    gxc.self_test()
    rng = random.Random(9347)
    reference = ''.join(rng.choices('ACGT', k=6848))
    _, anchor = reference, reference[3400:3431]
    assert reference.count(anchor) == 1
    reads = [
        (reference[100:] + reference[:100], '+', True, True),
        (gxc.rc(reference[2300:] + reference[:2300]), '-', True, True),
        (reference[4500:] + reference[:4500], '+', True, True),
        (reference[:3400] + 'A' * 31 + reference[3431:], '+', True, False),
        (reference + reference, '+', True, False),
        ('T' * 450, '+', False, False),
    ]
    class FakeRecord:
        def __init__(self, qname, seq):
            self.query_name = qname
            self.query_sequence = seq
            self.flag = 4
    fake = [FakeRecord(f'test_{i:05d}', r[0]) for i, r in enumerate(reads, 1)]
    class FakeAlignmentFile:
        def __init__(self, *a, **kw): self.index = 0
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def seek(self, off): self.index = int(off)
        def tell(self): return self.index
        def __iter__(self): return self
        def __next__(self):
            if self.index >= len(fake): raise StopIteration
            ret = fake[self.index]
            self.index += 1
            return ret
    sys.modules['pysam'] = types.SimpleNamespace(AlignmentFile=FakeAlignmentFile)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        bam = root / 'dummy.bam'
        bam.write_bytes(b'fake only, mocked pysam')
        ref_file = root / 'ref.fa'
        ref_file.write_text('>ref\n' + reference + '\n')
        mapped = root / 'mapped'
        mapped.mkdir()
        for ci in range(2):
            sl = reads[ci * 3:(ci + 1) * 3]
            source = mapped / f'chunk_{ci:05d}.reads.csv.gz'
            with gzip.open(source, 'wt', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['ordinal', 'bam_qname', 'length_bp', 'bam_flag', 'mapped', 'strand', 'full_span'])
                for j, (seq, strand, ismapped, full) in enumerate(sl):
                    ordinal = ci * 3 + j + 1
                    writer.writerow([ordinal, f'test_{ordinal:05d}', len(seq), 4, int(ismapped), strand, int(full)])
            marker = {'chunk_id': ci, 'source_type': 'bam', 'params_sha256': 'fake_original_mapping_hash',
                      'start': ci * 3, 'end': (ci + 1) * 3, 'exhausted': ci == 1,
                      'counts': {'bam_records_or_unique_rows': 3, 'mapped_unique_or_records': sum(int(x[2]) for x in sl)},
                      'read_csv_bytes': source.stat().st_size}
            (mapped / f'chunk_{ci:05d}.done.json').write_text(json.dumps(marker))
        args = ['--bam', str(bam), '--reference', str(ref_file), '--mapping-chunks', str(mapped),
                '--out', str(root / 'output'), '--scratch', str(root / 'tmp'), '--mapping-chunk-reads', '3', '--expected-reads', '6']
        gxc.main(args + ['--stage', 'normalize', '--max-chunks', '1'])
        assert len(list((root / 'output' / 'chunks').glob('*.normalized.done.json'))) == 1
        gxc.main(args + ['--stage', 'normalize'])
        gxc.main(args + ['--stage', 'normalize'])  # replay idempotence
        assert len(list((root / 'output' / 'chunks').glob('*.normalized.done.json'))) == 2
        gxc.main(args + ['--stage', 'aggregate'])
        result = json.loads((root / 'output' / 'circular_start_normalized_summary.json').read_text())
        assert result['all_bam_reads'] == 6, result
        assert result['all_mapped_reads'] == 5, result
        assert result['normalized_mapped_reads'] == 3, result
        assert result['normalized_full_span_reads'] == 3, result
        assert result['unresolved_mapped_reads'] == 2, result
        assert result['distinct_circular_normalized_sequences'] == 1, result
        with gzip.open(root / 'output' / 'mapped_circular_start_normalized_count.csv.gz', 'rt', newline='') as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1 and int(rows[0]['count']) == 3 and rows[0]['sequence'].startswith(anchor), rows
        print('PASS: rotation (+/-), exact grouping 3->1, non-unique anchor, mutated anchor, fullspan, resumability, count conservation')

if __name__ == '__main__':
    test()


def test_latest_three_only():
    """Old checkpoints are skipped on resume; newest three are SHA-verified."""
    import hashlib
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder)
        path = out / 'chunks'
        path.mkdir()
        manifest = 'identical_params_hash'
        for i in range(6):
            file = path / f'chunk_{i:05d}.normalized.csv.gz'
            file.write_bytes(b'fake gzip checkpoint bytes - ' + str(i).encode())
            marker = {'chunk_id': i, 'params_sha256': manifest,
                      'csv_name': file.name, 'csv_size': file.stat().st_size,
                      'csv_sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
            (path / f'chunk_{i:05d}.normalized.done.json').write_text(json.dumps(marker))
        assert gxc.completed_prefix(out, 8) == 6
        # Corrupt old payload but keep its size; newest-three policy does not reopen it.
        old = path / 'chunk_00000.normalized.csv.gz'
        old.write_bytes(b'fake gzip checkpoint bytes - X')
        assert old.stat().st_size == len(b'fake gzip checkpoint bytes - 0')
        for idx in range(3, 6):
            assert gxc.validate_existing(out, idx, manifest, verify_digest=True)
        assert gxc.validate_existing(out, 0, manifest, verify_digest=False)
        try:
            gxc.validate_existing(out, 0, manifest, verify_digest=True)
            raise AssertionError('Full SHA256 check failed to catch simulated old corruption')
        except ValueError as exc:
            assert 'SHA256 mismatch' in str(exc)
        # Incomplete staged file does not count toward the committed prefix.
        (path / 'chunk_00006.normalized.csv.gz.partial').write_bytes(b'')
        assert gxc.completed_prefix(out, 8) == 6
        status = gxc.write_normalization_progress(out, 'NORMALIZING', 6, 8)
        assert status['next_chunk_id'] == 6 and status['percent'] == 75.0
        print('PASS: newest-three digest verification, prefix resume, progress checkpoint')


if __name__ == '__main__':
    test_latest_three_only()
