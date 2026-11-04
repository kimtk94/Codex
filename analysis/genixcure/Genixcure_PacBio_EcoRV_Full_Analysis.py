#!/usr/bin/env python3
"""Resumable, exhaustive Genixcure PacBio HiFi -> EcoRV-linear reference audit.

Modes:
  --bam: reads EVERY BAM alignment record via pysam, with BGZF virtual-offset checkpoint.
  --unique-csv: reads EVERY exact-unique CSV row and uses read_count as frequency;
                sequence-level whole-population metrics but NOT BAM per-read QC.

Never treats UMI/Barcode feature labels as verified molecular IDs. This workflow
reports observed read-sequence patterns, not proven independent molecules.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

N_REF = 6848
EXPECTED_READS = 5_140_518
EXPECTED_UNIQUE_ROWS = 4_629_432
CIGAR = re.compile(r"(\d+)([MIDNSHP=X])")
COMP = str.maketrans('ACGTN', 'TGCAN')
WINDOWS = {
    'itr': (2110, 2280),
    'umi_A_candidate': (2428, 2442),
    'barcode_B_candidate': (2442, 2453),
    'additional_21_candidate': (6060, 6091),
}
QC_FIELDS = [
    'ordinal','bam_qname','read_count','length_bp','bam_flag','bam_rq','missing_sequence',
    'mapped','alignment_segments','strand','qcov','rcov','alignment_identity',
    'full_span','high_identity','itr_del_90_102',
    'umi_A_ins_10_14','barcode_B_ins_10_14','additional_ins_19_23',
    'umi_A_sequence','barcode_B_sequence','additional_sequence',
    'informative_matches','informative_mismatches','other_large_indels',
    'total_inserted_bases','total_deleted_bases',
]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_reference(path):
    seq = ''.join(line.strip().upper() for line in Path(path).read_text().splitlines() if not line.startswith('>'))
    if len(seq) != N_REF or set(seq) - set('ACGTN'):
        raise ValueError('Invalid reference FASTA: expected one 6848bp ACGTN sequence')
    return seq


def cigar_ops(cg):
    ops = [(int(n), op) for n, op in CIGAR.findall(cg)]
    if not ops or ''.join(str(n) + op for n, op in ops) != cg:
        raise ValueError('Malformed/partial CIGAR')
    return ops


def rc(seq):
    return seq.translate(COMP)[::-1]


def overlap(a, b, region):
    return max(0, min(b,region[1]) - max(a,region[0]))


def parse_alignment(fields, seq, ref):
    qlen, qs, qe = map(int,(fields[1],fields[2],fields[3]))
    tlen, ts, te = map(int,(fields[6],fields[7],fields[8]))
    if tlen != len(ref) or qlen != len(seq):
        raise ValueError('Reference/query lengths mismatch')
    cg = next((tag[5:] for tag in fields[12:] if tag.startswith('cg:Z:')), None)
    if not cg:
        raise ValueError('minimap2 did not provide cg:Z CIGAR')
    strand = fields[4]
    if strand not in ('+','-'):
        raise ValueError('Invalid PAF strand')
    oriented = seq if strand=='+' else rc(seq)
    qpos = qs if strand=='+' else qlen-qe
    rpos = ts
    matches = mismatches = n_insert = n_delete = 0
    flags = {key: False for key in ('itr_del_90_102','umi_A_ins_10_14','barcode_B_ins_10_14','additional_ins_19_23')}
    seqs = {'umi_A_sequence':'','barcode_B_sequence':'','additional_sequence':''}
    other_large_indels = 0
    for n,op in cigar_ops(cg):
        if op in ('M','=','X'):
            a = oriented[qpos:qpos+n]
            b = ref[rpos:rpos+n]
            if len(a)!=n or len(b)!=n:
                raise ValueError('CIGAR alignment overrun')
            # minimap2 --eqx marks exact matches (=) and mismatches (X).
            # Fast path avoids a Python-level loop across ~35 billion aligned bases.
            informative=n-b.count('N')
            if op=='=': matches+=informative
            elif op=='X': mismatches+=informative
            else:
                for x,y in zip(a,b):
                    if y=='N':continue
                    if x==y:matches+=1
                    else:mismatches+=1
            qpos+=n; rpos+=n
        elif op=='I':
            n_insert+=n
            insertion = oriented[qpos:qpos+n]
            if len(insertion)!=n:raise ValueError('Insertion overrun')
            if 10<=n<=14 and 2428<=rpos<2442:
                flags['umi_A_ins_10_14']=True
                if len(insertion)>len(seqs['umi_A_sequence']):seqs['umi_A_sequence']=insertion
            if 10<=n<=14 and 2442<=rpos<2453:
                flags['barcode_B_ins_10_14']=True
                if len(insertion)>len(seqs['barcode_B_sequence']):seqs['barcode_B_sequence']=insertion
            if 19<=n<=23 and 6060<=rpos<6091:
                flags['additional_ins_19_23']=True
                if len(insertion)>len(seqs['additional_sequence']):seqs['additional_sequence']=insertion
            if n>=10 and not any(start<=rpos<end for name,(start,end) in WINDOWS.items() if name!='itr'):
                other_large_indels+=1
            qpos+=n
        elif op in ('D','N'):
            n_delete+=n
            if 90<=n<=102 and overlap(rpos,rpos+n,WINDOWS['itr'])>0:
                flags['itr_del_90_102']=True
            if n>=10 and overlap(rpos,rpos+n,WINDOWS['itr'])==0:
                other_large_indels+=1
            rpos+=n
        elif op=='S':
            qpos+=n
        elif op in ('H','P'):
            continue
        else:
            raise ValueError('Unsupported CIGAR op')
    expected_q_end = qe if strand=='+' else qlen-qs
    if qpos!=expected_q_end or rpos!=te:
        raise ValueError(f'CIGAR span mismatch: qpos={qpos}, expected={expected_q_end}, ref={rpos}, expected={te}')
    qcov=(qe-qs)/qlen if qlen else 0
    rcov=(te-ts)/len(ref)
    ident=matches/(matches+mismatches) if (matches+mismatches) else 0
    full_span=bool(0.8*N_REF<=qlen<=1.25*N_REF and qcov>=.9 and rcov>=.9 and ts<=150 and N_REF-te<=150)
    return {
        'strand':strand,'qcov':round(qcov,6),'rcov':round(rcov,6),
        'alignment_identity':round(ident,6),'full_span':int(full_span),
        'high_identity':int(ident>=0.999),
        **{k:int(v) for k,v in flags.items()},**seqs,
        'informative_matches':matches,'informative_mismatches':mismatches,
        'other_large_indels':other_large_indels,
        'total_inserted_bases':n_insert,'total_deleted_bases':n_delete,
    }


def parse_paf(path, seq_by_id, ref):
    best={}; segments=collections.Counter()
    with Path(path).open() as f:
        for line in f:
            v=line.rstrip('\n').split('\t')
            if len(v)<12:continue
            key=v[0]
            if key not in seq_by_id:raise ValueError('Unexpected PAF query ID '+key)
            if 'tp:A:S' in v[12:]:continue  # secondary only
            segments[key]+=1
            score=(int(v[3])-int(v[2]),int(v[9]),int(v[11]))
            if key not in best or score>best[key][0]:best[key]=(score,v)
    align={k:parse_alignment(value[1],seq_by_id[k],ref) for k,value in best.items()}
    return align,segments


def create_batch_fasta(entries,path):
    with Path(path).open('w') as out:
        for entry in entries:
            out.write('>'+entry['id']+'\n')
            seq=entry['sequence']
            for j in range(0,len(seq),100):out.write(seq[j:j+100]+'\n')


def atomic_copy(src,dest):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    staged=dest.with_suffix(dest.suffix+'.partial')
    shutil.copyfile(src,staged)
    if staged.stat().st_size!=Path(src).stat().st_size:
        raise RuntimeError('Drive copy size mismatch '+str(dest))
    staged.replace(dest)


def summarize_counts(entries,align,segments):
    metrics=collections.Counter()
    metrics['bam_records_or_unique_rows']=len(entries)
    metrics['weighted_reads']=sum(e['weight'] for e in entries)
    metrics['missing_sequence_records']=sum(int(e.get('missing_sequence',False)) for e in entries)
    metrics['bam_secondary_supplementary_records']=sum(int(bool(e['flag'] & (0x100|0x800))) for e in entries if isinstance(e['flag'],int))
    metrics['bam_originally_unmapped_records']=sum(int(bool(e['flag'] & 0x4)) for e in entries if isinstance(e['flag'],int))
    for entry in entries:
        w=entry['weight'];q=entry['id'];a=align.get(q)
        if not a:
            metrics['unmapped_unique_or_records']+=1
            metrics['unmapped_weighted_reads']+=w
            continue
        metrics['mapped_unique_or_records']+=1
        metrics['mapped_weighted_reads']+=w
        metrics['informative_matches']+=a['informative_matches']*w
        metrics['informative_mismatches']+=a['informative_mismatches']*w
        for flag in ('full_span','high_identity','itr_del_90_102','umi_A_ins_10_14','barcode_B_ins_10_14','additional_ins_19_23'):
            if a[flag]:
                metrics[flag+'_unique_or_records']+=1
                metrics[flag+'_weighted_reads']+=w
        if segments[q]>1:
            metrics['multi_segment_unique_or_records']+=1
            metrics['multi_segment_weighted_reads']+=w
        if a['umi_A_ins_10_14'] and a['barcode_B_ins_10_14']:
            metrics['both_variable_12bp_weighted_reads']+=w
            metrics['both_variable_12bp_unique_or_records']+=1
        if a['itr_del_90_102'] and a['umi_A_ins_10_14'] and a['barcode_B_ins_10_14'] and a['additional_ins_19_23']:
            metrics['all_four_events_unique_or_records']+=1
            metrics['all_four_events_weighted_reads']+=w
    return dict(metrics)


def process_chunk(entries, chunk_id, ref_path, ref, out_dir, work, params_hash, start_marker,end_marker,exhausted,source_type,threads):
    work.mkdir(parents=True,exist_ok=True)
    tmpfa=work/'batch.fasta';tmppaf=work/'batch.paf';tmplog=work/'batch.minimap2.log';tmpcsv=work/'batch.reads.csv.gz'
    create_batch_fasta(entries,tmpfa)
    cmd=['minimap2','-x','map-hifi','--secondary=no','--eqx','-c','-t',str(threads),str(ref_path),str(tmpfa)]
    print(f'[CHUNK {chunk_id:05d}] aligning {len(entries):,} unique rows/records',flush=True)
    with tmppaf.open('w') as stdout,tmplog.open('w') as stderr:
        returncode=subprocess.call(cmd,stdout=stdout,stderr=stderr)
    if returncode:
        raise RuntimeError('minimap2 exit {}: {}'.format(returncode,tmplog.read_text(errors='replace')[-4000:]))
    seq_by_id={e['id']:e['sequence'] for e in entries}
    align,segments=parse_paf(tmppaf,seq_by_id,ref)
    with gzip.open(tmpcsv,'wt',newline='',compresslevel=2) as f:
        writer=csv.DictWriter(f,fieldnames=QC_FIELDS);writer.writeheader()
        for e in entries:
            a=align.get(e['id'])
            row={'ordinal':e['ordinal'],'bam_qname':e['qname'], 'read_count':e['weight'],
                 'length_bp':len(e['sequence']),'bam_flag':e['flag'],'bam_rq':e['rq'],
                 'missing_sequence':int(e.get('missing_sequence',False)),
                 'mapped':int(a is not None),'alignment_segments':segments[e['id']]}
            if a:row.update(a)
            writer.writerow(row)
    counts=summarize_counts(entries,align,segments)
    chunk_name=f'chunk_{chunk_id:05d}'
    chunkdir=out_dir/'chunks';chunkdir.mkdir(parents=True,exist_ok=True)
    report=chunkdir/(chunk_name+'.reads.csv.gz')
    atomic_copy(tmpcsv,report)
    # Retain raw PAF losslessly for complete post-hoc CIGAR validation.
    paf_gzip=work/'batch.paf.gz'
    with tmppaf.open('rb') as fi,gzip.open(paf_gzip,'wb',compresslevel=1) as fo:
        shutil.copyfileobj(fi,fo,1024*1024)
    paf_output=chunkdir/(chunk_name+'.paf.gz')
    atomic_copy(paf_gzip,paf_output)
    checksum=sha256(report)
    marker={
        'chunk_id':chunk_id,'source_type':source_type,'params_sha256':params_hash,
        'start':start_marker,'end':end_marker,'exhausted':exhausted,
        'counts':counts,'read_csv_bytes':report.stat().st_size,
        'read_csv_sha256':checksum,'paf_gzip_bytes':paf_output.stat().st_size,
    }
    marker_tmp=work/'done.json';marker_tmp.write_text(json.dumps(marker,ensure_ascii=False,indent=2))
    # JSON marker is the LAST commit: orphaned stage outputs are safe to overwrite on retry.
    atomic_copy(marker_tmp,chunkdir/(chunk_name+'.done.json'))
    print(f"[CHUNK {chunk_id:05d}] committed; aligned={counts.get('mapped_unique_or_records',0):,}; total weighted={counts['weighted_reads']:,}",flush=True)
    return marker


def read_checkpoints(out_dir,source_type,params_hash):
    folder=out_dir/'chunks';folder.mkdir(parents=True,exist_ok=True)
    all_done=sorted(folder.glob('chunk_*.done.json'))
    checkpoints=[]
    for expected_idx,path in enumerate(all_done,0):
        d=json.loads(path.read_text())
        if d['chunk_id']!=expected_idx:raise RuntimeError('Non-contiguous checkpoint chunks: '+path.name)
        if d['params_sha256']!=params_hash or d['source_type']!=source_type:
            raise RuntimeError('Resume parameters mismatch. Preserve folder and use a separate OUT directory.')
        if checkpoints and d['start']!=checkpoints[-1]['end']:
            raise RuntimeError('Resume source boundary mismatch. Stop to prevent read loss or duplication.')
        csvfile=folder/f'chunk_{expected_idx:05d}.reads.csv.gz'
        paf=folder/f'chunk_{expected_idx:05d}.paf.gz'
        if not csvfile.exists() or not paf.exists() or csvfile.stat().st_size!=d['read_csv_bytes']:
            raise RuntimeError('Missing or damaged checkpoint files: '+str(path))
        checkpoints.append(d)
    return checkpoints


def aggregate(checkpoints,out_dir,source_type,params_hash,finished=False):
    all_metrics=collections.Counter()
    for d in checkpoints:all_metrics.update(d['counts'])
    total=all_metrics['weighted_reads']
    status='RUNNING'
    if finished:
        if total!=EXPECTED_READS or (source_type=='unique_csv' and all_metrics['bam_records_or_unique_rows']!=EXPECTED_UNIQUE_ROWS):
            status='HOLD_READ_COUNT_MISMATCH'
        else:
            status='FULL_DATASET_COMPLETE'
    res={
        'status':status,'input_mode':source_type,'input_scope':('all BAM records' if source_type=='bam' else 'all unique CSV rows weighted by read_count'),
        'chunks_committed':len(checkpoints),'expected_reads_from_prior_report':EXPECTED_READS,
        'observed_total_reads':total,'metrics':dict(all_metrics),
        'params_sha256':params_hash,'source_complete':bool(finished),
        'limitations':[
            'Full unique CSV loses raw read name, per-base qualities, and per-read polymerase metadata; separate BAM mode is necessary for raw-level validation.' if source_type=='unique_csv' else 'BAM record-based statistics require QC of alignment flags and read quality tags before interpreting independent molecules.',
            'UMI/Barcode labels are unverified; inserted sequence patterns are not UMI-corrected molecule counts.',
            'Full-span reference mapping alone does not prove intact or functional plasmid.',
            'ITR repetitive structure can shift CIGAR breakpoints; structural events remain alignment-defined.',
        ]}
    outfile=out_dir/'full_run_progress.json' if not finished else out_dir/'full_run_final_summary.json'
    tmppath=outfile.with_suffix('.json.partial')
    tmppath.write_text(json.dumps(res,ensure_ascii=False,indent=2))
    tmppath.replace(outfile)
    print(f'[PROGRESS] source={source_type}, committed={len(checkpoints)}, reads={total:,}/{EXPECTED_READS:,}, status={status}',flush=True)
    return res


def bam_runner(args, ref, params_hash):
    try:
        import pysam
    except ImportError as exc:
        raise RuntimeError('pysam required for BAM mode. Install with pip install pysam') from exc
    bam=Path(args.bam)
    if not bam.is_file() or bam.stat().st_size<1_000_000_000:
        raise RuntimeError('BAM path not present/readable or appears truncated: '+str(bam))
    checkpoints=read_checkpoints(args.out,'bam',params_hash)
    prev=checkpoints[-1] if checkpoints else None
    if prev and prev['exhausted']:
        return aggregate(checkpoints,args.out,'bam',params_hash,True)
    ordinal=sum(x['counts']['bam_records_or_unique_rows'] for x in checkpoints)
    with pysam.AlignmentFile(str(bam),'rb',check_sq=False) as stream:
        if prev:
            stream.seek(int(prev['end']))
        it=iter(stream)
        while True:
            start=int(stream.tell())
            batch=[];eof=False
            for _ in range(args.chunk_reads):
                try: record=next(it)
                except StopIteration:
                    eof=True;break
                ordinal+=1
                seq=record.query_sequence
                missing_sequence=(seq is None)
                if seq is None:
                    # Preserve the record, but unmappable missing sequence is an explicit category.
                    seq='N'
                qname=record.query_name or ''
                try:rq=record.get_tag('rq')
                except KeyError:rq=''
                batch.append({'id':f'read_{ordinal:012d}','ordinal':ordinal,'qname':qname,
                              'sequence':seq.upper(),'weight':1,'flag':record.flag,'rq':rq,
                              'missing_sequence':missing_sequence})
            end=int(stream.tell())
            if not batch:
                return aggregate(checkpoints,args.out,'bam',params_hash,True)
            d=process_chunk(batch,len(checkpoints),args.reference,ref,args.out,args.temp,params_hash,
                            start,end,eof,'bam',args.threads)
            checkpoints.append(d);aggregate(checkpoints,args.out,'bam',params_hash,eof)
            if eof:return aggregate(checkpoints,args.out,'bam',params_hash,True)
            if args.max_chunks and len(checkpoints)>=args.max_chunks:
                return aggregate(checkpoints,args.out,'bam',params_hash,False)


def csv_runner(args,ref,params_hash):
    checkpoints=read_checkpoints(args.out,'unique_csv',params_hash)
    prev=checkpoints[-1] if checkpoints else None
    if prev and prev['exhausted']:
        return aggregate(checkpoints,args.out,'unique_csv',params_hash,True)
    ordinal=int(prev['end']) if prev else 0
    with gzip.open(args.unique_csv,'rt',newline='') as reader:
        csvreader=csv.DictReader(reader)
        if csvreader.fieldnames!=['sequence','read_count','length_bp']:
            raise ValueError('Wrong unique CSV schema: '+str(csvreader.fieldnames))
        for _ in range(ordinal):
            try:next(csvreader)
            except StopIteration:raise RuntimeError('CSV shorter than checkpoint rows')
        while True:
            start=ordinal;batch=[];eof=False
            for _ in range(args.chunk_reads):
                try:row=next(csvreader)
                except StopIteration:eof=True;break
                ordinal+=1
                seq=row['sequence'].upper();ct=int(row['read_count'])
                if ct<1 or len(seq)!=int(row['length_bp']) or not seq or set(seq)-set('ACGTN'):
                    raise ValueError('Invalid unique CSV row '+str(ordinal))
                batch.append({'id':f'uniq_{ordinal:012d}','ordinal':ordinal,'qname':'',
                              'sequence':seq,'weight':ct,'flag':'','rq':''})
            if not batch:return aggregate(checkpoints,args.out,'unique_csv',params_hash,True)
            d=process_chunk(batch,len(checkpoints),args.reference,ref,args.out,args.temp,params_hash,
                            start,ordinal,eof,'unique_csv',args.threads)
            checkpoints.append(d);aggregate(checkpoints,args.out,'unique_csv',params_hash,eof)
            if eof:return aggregate(checkpoints,args.out,'unique_csv',params_hash,True)
            if args.max_chunks and len(checkpoints)>=args.max_chunks:
                return aggregate(checkpoints,args.out,'unique_csv',params_hash,False)


def self_test():
    assert cigar_ops('5=96D10=12I21X')==[(5,'='),(96,'D'),(10,'='),(12,'I'),(21,'X')]
    assert rc('ACGTN')=='NACGT'
    # Synthetic + and - observations, without making reference sequence biological claims.
    ref='A'*N_REF
    q='A'*20+'G'*12+'A'*20
    cg='20=12I20='
    paf=['s',str(len(q)),'0',str(len(q)),'+','ref',str(N_REF),'2410','2450','40','52','60','cg:Z:'+cg]
    obs=parse_alignment(paf,q,ref)
    assert obs['umi_A_ins_10_14']==1 and obs['umi_A_sequence']=='G'*12
    assert obs['informative_matches']==40 and obs['full_span']==0
    # Mapping conversion is fixed with EcoRV cut: original coordinate 3948 = linear 6079 (zero-based)
    assert ((4716+6079)%6848)+1==3948
    print('FULL ANALYSIS SYNTHETIC SELF TEST PASS')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    inputs=p.add_mutually_exclusive_group()
    inputs.add_argument('--bam',type=Path)
    inputs.add_argument('--unique-csv',type=Path)
    p.add_argument('--reference',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('--temp',type=Path,default=Path('/content/genixcure_full_pacbio_tmp'))
    p.add_argument('--chunk-reads',type=int,default=10000)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--max-chunks',type=int,default=0,help='0=all; otherwise stop cleanly after N committed chunks')
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args(argv)
    if args.self_test:return self_test()
    if not args.bam and not args.unique_csv:p.error('Choose --bam or --unique-csv')
    if not args.reference or not args.out:p.error('--reference and --out are mandatory')
    if args.chunk_reads<=0 or args.threads<=0:raise ValueError('Positive chunks/threads required')
    if not shutil.which('minimap2'):raise RuntimeError('minimap2 executable unavailable')
    ref=read_reference(args.reference)
    args.out.mkdir(parents=True,exist_ok=True)
    args.temp.mkdir(parents=True,exist_ok=True)
    source_type='bam' if args.bam else 'unique_csv'
    path=args.bam if args.bam else args.unique_csv
    if not path.is_file():raise FileNotFoundError(path)
    params={
        'reference_sha256':sha256(args.reference), 'source_type':source_type,
        'source_filename':path.name, 'source_size':path.stat().st_size,
        'expected_read_count':EXPECTED_READS, 'expected_unique_rows':EXPECTED_UNIQUE_ROWS,
        'chunk_reads':args.chunk_reads,
        'pipeline_version':'Genixcure_Full_EcoRV_v1.0.0',
        'alignment_parameters':['-x','map-hifi','--secondary=no','--eqx','-c'],
    }
    fingerprint=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
    manifest=args.out/'pipeline_parameters.json'
    if manifest.exists():
        prior=json.loads(manifest.read_text())
        if prior.get('params_sha256')!=fingerprint:
            raise RuntimeError('Existing output folder belongs to DIFFERENT pipeline parameters. Use another output folder.')
    else:
        manifest.write_text(json.dumps({**params,'params_sha256':fingerprint},indent=2))
    if source_type=='bam':return bam_runner(args,ref,fingerprint)
    return csv_runner(args,ref,fingerprint)

if __name__=='__main__':main()
