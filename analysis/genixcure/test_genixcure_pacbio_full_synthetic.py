#!/usr/bin/env python3
"""No-private-data end-to-end regression of full-dataset checkpoint pipeline."""
import csv
import gzip
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name('Genixcure_PacBio_EcoRV_Full_Analysis.py')

def run():
    with tempfile.TemporaryDirectory() as work:
        w = Path(work)
        stub = w / 'minimap2'
        stub.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
f=Path(sys.argv[-1]); rid=None; seq=[]
def emit():
 if rid is None: return
 s=''.join(seq);n=len(s)
 print(f"{rid}\\t{n}\\t0\\t{n}\\t+\\tref\\t6848\\t2000\\t{2000+n}\\t{n}\\t{n}\\t60\\tcg:Z:{n}=")
for row in f.open():
 row=row.strip()
 if row.startswith('>'):
  emit();rid=row[1:];seq=[]
 else:seq.append(row)
emit()
''')
        stub.chmod(0o755)
        reference = w/'reference.fa'
        reference.write_text('>ref\n' + 'A'*6848 + '\n')
        source = w/'test.csv.gz'
        with gzip.open(source,'wt') as f:
            f.write('sequence,read_count,length_bp\n')
            for seq,ct in [('A'*50,3),('A'*60,2),('A'*70,1)]:
                f.write(f'{seq},{ct},{len(seq)}\n')
        out = w/'out'
        cmd=[sys.executable,str(SCRIPT),'--unique-csv',str(source),
             '--reference',str(reference),'--out',str(out),'--chunk-reads','2','--threads','1']
        env=dict(os.environ, PATH=str(w)+os.pathsep+os.environ.get('PATH',''))
        res=subprocess.run(cmd,env=env,capture_output=True,text=True)
        assert res.returncode==0,(res.stdout,res.stderr)
        result=json.loads((out/'full_run_final_summary.json').read_text())
        assert result['status']=='HOLD_READ_COUNT_MISMATCH',result
        assert result['observed_total_reads']==6
        assert result['metrics']['mapped_weighted_reads']==6
        assert result['metrics']['bam_records_or_unique_rows']==3
        assert result['chunks_committed']==2
        # Verify replay causes no duplicate count; contiguous chunks kept.
        res2=subprocess.run(cmd,env=env,capture_output=True,text=True)
        assert res2.returncode==0,(res2.stdout,res2.stderr)
        assert len(list((out/'chunks').glob('*.done.json')))==2
        assert json.loads((out/'full_run_final_summary.json').read_text())['observed_total_reads']==6
        print('FULL PIPELINE SYNTHETIC END-TO-END PASS: two chunks, six weighted reads, no duplicate replay, mismatch HOLD')

if __name__=='__main__':run()
