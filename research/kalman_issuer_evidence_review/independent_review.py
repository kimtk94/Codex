"""Independently re-extract pinned source text; research diagnostics only."""
import argparse
import gzip
from html.parser import HTMLParser
from html import unescape
import io
import json
from pathlib import PurePosixPath, Path
import re
import zipfile
from evidence_review import TARGETS, VERIFIED, REPORT_SUFFIX, inspect_archive, read_member, compare, sha

ANCHORS = {
    "QQQ_2018_SEC_2020_Q3_TABLE": ("2018 First Quarter $174.08 $153.45", "0.37837"),
    "QLD_2025_FORM_8937_SPLIT": ("November 19, 2025", "2:1 share split"),
}

class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def extract_text(raw, kind):
    if kind == "html":
        p = VisibleHTML()
        p.feed(raw.decode("utf-8-sig", errors="replace"))
        p.close()
        return " ".join(unescape(" ".join(p.parts)).split())
    from pypdf import PdfReader
    pdf = PdfReader(io.BytesIO(raw), strict=False)
    return " ".join(" ".join((page.extract_text() or "") for page in
                             pdf.pages[:18]).split())

def anchors_near(text, anchors):
    a, b = [x.lower() for x in anchors]
    t = text.lower()
    aa = [m.start() for m in re.finditer(re.escape(a), t)]
    bb = [m.start() for m in re.finditer(re.escape(b), t)]
    return bool(aa and bb and min(abs(x-y) for x in aa for y in bb) <= 1800)

def independent_review(path, pin):
    report = inspect_archive(path, pin)
    # Read same bytes and verify outer pin again; no extraction to disk.
    payload = Path(path).read_bytes()
    if sha(payload) != pin:
        raise ValueError("ARCHIVE_PIN_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        rp = next(n for n in z.namelist() if n == REPORT_SUFFIX or n.endswith("/"+REPORT_SUFFIX))
        prefix = str(PurePosixPath(rp).parent)
        for sid, (_, _, kind, limit) in TARGETS.items():
            item = report["sources"][sid]
            item["independent_anchors_verified"] = False
            if item["state"] != VERIFIED:
                continue
            member = prefix + "/raw/" + sid.lower() + "." + kind + ".gz"
            compressed = read_member(z, member, limit + 1_000_000)
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f:
                raw = f.read(limit + 1)
            if len(raw) > limit or sha(raw) != item["sha256"]:
                raise ValueError("REEXTRACTION_BYTES_MISMATCH")
            try:
                text = extract_text(raw, kind)
                item["independent_anchors_verified"] = anchors_near(text, ANCHORS[sid])
                item["independent_text_sha256"] = sha(text.encode())
            except Exception as exc:
                item["extraction_error_type"] = type(exc).__name__
            if not item["independent_anchors_verified"]:
                item["state"] = "INDEPENDENT_ANCHORS_FAILED_HOLD"
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("current")
    p.add_argument("prior")
    p.add_argument("--current-sha256", required=True)
    p.add_argument("--prior-sha256", required=True)
    args = p.parse_args()
    current = independent_review(args.current, args.current_sha256)
    prior = independent_review(args.prior, args.prior_sha256)
    result = compare(current, prior)
    print(json.dumps({"current":current,"prior":prior,"comparison":result},sort_keys=True))
    # A verified pair is a research prerequisite, never cache authorization.
    if not result["prior_pair_available"]:
        raise SystemExit("PRIOR_PAIR_INDEPENDENT_REVIEW_HOLD")

if __name__ == "__main__":
    main()
