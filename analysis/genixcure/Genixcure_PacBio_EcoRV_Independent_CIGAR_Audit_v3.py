#!/usr/bin/env python3
"""Independent read-only EcoRV linear plasmid HiFi CIGAR review.
Never infers molecule/UMI identity from mere alignment or annotation labels.
Original plasmid coord = ((4716 + linear_0based) % 6848) + 1.
"""
import argparse
import collections
import csv
import json
import re
from pathlib import Path

CIGAR = re.compile(r"(\d+)([MIDNSHP=X])")
COMP = str.maketrans("ACGTN", "TGCAN")
WINDOWS = {
    "itr": (2100, 2280),
    "variable_A": (2428, 2442),
    "variable_B": (2442, 2453),
    "additional": (6060, 6091),
}
def rc(s):
    return s.translate(COMP)[::-1]

def original_position(ref0):
    return ((4716 + ref0) % 6848) + 1

def parse_cigar(cg):
    ops = [(int(k), v) for k, v in CIGAR.findall(cg)]
    if not ops or "".join(str(k) + v for k, v in ops) != cg:
        raise ValueError("Invalid CIGAR")
    return ops

def choose_primary(path):
    best = {}
    segments = collections.Counter()
    for line in Path(path).open():
        v = line.rstrip("\n").split("\t")
        if len(v) < 12 or "tp:A:S" in v[12:]:
            continue
        segments[v[0]] += 1
        score = (int(v[3]) - int(v[2]), int(v[9]), int(v[11]))
        if v[0] not in best or score > best[v[0]][0]:
            best[v[0]] = (score, v)
    return {q: x[1] for q, x in best.items()}, segments

def read_fasta(path):
    out = {}
    name = None
    with Path(path).open() as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                name = line[1:].split()[0]
                if name in out:
                    raise ValueError("Duplicate FASTA identifier " + name)
                out[name] = ""
            elif name:
                out[name] += line.upper()
    return out

def reference_fasta(path):
    records = read_fasta(path)
    if len(records) != 1:
        raise ValueError("Expected exactly one reference")
    seq = next(iter(records.values()))
    if len(seq) != 6848:
        raise ValueError("Unexpected reference length")
    return seq

def inspect_one(v, query, ref):
    qlen, qs, qe = (int(v[i]) for i in (1, 2, 3))
    rstart, rend = int(v[7]), int(v[8])
    if qlen != len(query):
        raise ValueError("Query length mismatch")
    cigar = next((x[5:] for x in v[12:] if x.startswith("cg:Z:")), None)
    if not cigar:
        raise ValueError("Missing cg:Z CIGAR")
    oriented = query if v[4] == "+" else rc(query)
    qpos = qs if v[4] == "+" else qlen - qe
    rpos = rstart
    observed_equal = equal_mismatch = substitutions = 0
    sites = {name: [] for name in WINDOWS}
    for n, op in parse_cigar(cigar):
        if op in ("M", "=", "X"):
            if op == "=":
                aa = oriented[qpos:qpos+n]
                bb = ref[rpos:rpos+n]
                observed_equal += n
                equal_mismatch += sum(x != y for x,y in zip(aa,bb))
            if op == "X":
                substitutions += n
            qpos += n
            rpos += n
        elif op == "I":
            for name, (start, end) in WINDOWS.items():
                if start <= rpos < end:
                    sites[name].append({"pos":rpos, "n":n, "sequence":oriented[qpos:qpos+n]})
            qpos += n
        elif op in ("D", "N"):
            for name, (start, end) in WINDOWS.items():
                if start <= rpos < end:
                    sites[name].append({"pos":rpos, "n":n, "type":"deletion"})
            rpos += n
        elif op == "S":
            qpos += n
    expected_qend = qe if v[4] == "+" else qlen - qs
    if qpos != expected_qend or rpos != rend:
        raise ValueError("CIGAR span mismatch")
    if equal_mismatch:
        raise ValueError(f"{equal_mismatch} unexpected sequence mismatches in '=' CIGAR runs")
    itr_96 = any(x.get("type") == "deletion" and 90 <= x["n"] <= 102 for x in sites["itr"])
    a_12 = any(x.get("type") != "deletion" and 10 <= x["n"] <= 14 for x in sites["variable_A"])
    b_12 = any(x.get("type") != "deletion" and 10 <= x["n"] <= 14 for x in sites["variable_B"])
    extra_21 = any(x.get("type") != "deletion" and 19 <= x["n"] <= 23 for x in sites["additional"])
    return {"eq":observed_equal,"x":substitutions,
            "itr96":itr_96,"variableA12":a_12,"variableB12":b_12,
            "extra21":extra_21,"sites":sites, "strand":v[4], 
            "full_span": (0.8*6848<=qlen<=1.25*6848 and (qe-qs)/qlen>=.9 
                          and (rend-rstart)/6848>=.9 and rstart<=150 and 6848-rend<=150)}

def audit(ref_file, read_file, paf_file, metadata_file, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    ref = reference_fasta(ref_file)
    reads = read_fasta(read_file)
    meta = {}
    for r in csv.DictReader(Path(metadata_file).open()):
        if r["query_id"] in meta:
            raise ValueError("Duplicate metadata ID")
        meta[r["query_id"]] = int(r["read_count"])
    if set(reads) != set(meta):
        raise ValueError("FASTA/metadata mismatch")
    selected, segments = choose_primary(paf_file)
    n_unique = len(reads)
    if set(selected) - set(reads):
        raise ValueError("PAF has unknown query IDs")
    flags = collections.Counter()
    weighted = collections.Counter()
    insert_sequences = {k:collections.Counter() for k in WINDOWS}
    insertion_events = collections.Counter()
    deletion_events = collections.Counter()
    combinations = collections.Counter()
    n_equal = n_x = 0
    rows = []
    for q, v in selected.items():
        obs = inspect_one(v,reads[q],ref)
        n_equal += obs["eq"]
        n_x += obs["x"]
        for flag in ("itr96","variableA12","variableB12","extra21","full_span"):
            flags[flag] += int(obs[flag])
            weighted[flag] += meta[q] * int(obs[flag])
        combos = (obs["itr96"],int(obs["variableA12"])+int(obs["variableB12"]),obs["extra21"])
        combinations[str(combos)] += 1
        for name,events in obs["sites"].items():
            for evt in events:
                key = (name, evt["pos"], evt["n"])
                if evt.get("type") == "deletion":
                    deletion_events[key] += 1
                else:
                    insertion_events[key] += 1
                    insert_sequences[name][evt["sequence"]] += 1
        rows.append({"query_id":q,"read_count":meta[q],
                     "itr96":int(obs["itr96"]),"variable_A_12":int(obs["variableA12"]),
                     "variable_B_12":int(obs["variableB12"]),"additional_21":int(obs["extra21"]),
                     "full_span":int(obs["full_span"]),
                     "eq_bases":obs["eq"],"x_bases":obs["x"],
                     "nonsecondary_segments":segments[q]})
    def top_events(data, k=20):
        return [{"region":site,"ref_0based":p,"plasmid_original_1based":original_position(p),
                 "length_bp":n,"unique":ct}
                for (site,p,n),ct in data.most_common(k)]
    result = {
        "status":"INDEPENDENT_CIGAR_REVIEW_COMPLETE",
        "sample_type":"weighted-unique pilot (not a read-random population sample)",
        "reference_bp":len(ref),"sample_unique":n_unique,
        "mapped_unique":len(selected),"unmapped_unique":n_unique-len(selected),
        "sample_read_count_sum":sum(meta.values()),
        "mapped_sample_read_count_sum":sum(meta[q] for q in selected),
        "counts":dict(flags),"weighted_observed_counts":dict(weighted),
        "exact_match_bases":n_equal,"mismatch_bases":n_x,
        "aligned_substitution_identity_excluding_indels":n_equal/(n_equal+n_x),
        "events_top_insertions":top_events(insertion_events,40),
        "events_top_deletions":top_events(deletion_events,30),
        "event_combinations_unique":dict(combinations),
        "distinct_insertion_sequences":{k:len(c) for k,c in insert_sequences.items()},
        "notes":[
            "UMI/Barcode reference feature labels span 2bp each, but distinct ~12bp inserted segments are observed at two near-feature sites.",
            "A recurrent ~21bp insertion near original plasmid position 3948 was absent from the prior v2 summary.",
            "ITR repetitive structure can shift the precise gap placement; do not overinterpret a single aligner CIGAR breakpoint.",
            "The aligned substitution concordance does not measure intact construct rate or a raw HiFi sequencing error rate.",
            "Some mappings contain supplementary/split segments; this audit chooses one representative nonsecondary segment only."
        ]
    }
    (out/"independent_CIGAR_audit_v3.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with (out/"independent_CIGAR_read_flags_v3.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    print(json.dumps({k:result[k] for k in ("sample_unique","mapped_unique","counts","exact_match_bases","mismatch_bases","aligned_substitution_identity_excluding_indels")},indent=2))
    return result

def self_test():
    assert original_position(2144)==13
    assert original_position(2438)==307
    assert original_position(2446)==315
    assert original_position(6079)==3948
    assert parse_cigar("20=96D30=12I15X")==[(20,"="),(96,"D"),(30,"="),(12,"I"),(15,"X")]
    try:
        parse_cigar("20=gibberish")
    except ValueError:
        pass
    else:
        raise AssertionError("CIGAR parser accepted malformed input")
    print("SELF TEST PASS")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--reference",type=Path)
    ap.add_argument("--fasta",type=Path)
    ap.add_argument("--paf",type=Path)
    ap.add_argument("--metadata",type=Path)
    ap.add_argument("--out",type=Path)
    args=ap.parse_args()
    if args.self_test:
        self_test()
    else:
        if not all((args.reference,args.fasta,args.paf,args.metadata,args.out)):
            ap.error("--reference --fasta --paf --metadata --out are all required")
        audit(args.reference,args.fasta,args.paf,args.metadata,args.out)
