"""Download ~10 Xeno-canto clips per indicator species into test_clips/<id>/.

Xeno-canto API v3 needs a personal key (https://xeno-canto.org/account).
Never commit it. Usage:
    XC_API_KEY=... python scripts/fetch_bird_clips.py [--per-species 10]
"""
import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from suokuulo.config import load_species  # noqa: E402

API = "https://xeno-canto.org/api/3/recordings"
CREDIT_FIELDS = ["file", "label", "source", "recordist", "licence", "url"]
# Tried in order until we have enough clips: best quality and short first.
QUERIES = ['q:A len:"<60"', 'q:B len:"<60"', "q:A", "q:B"]


def update_credits(rows, path="credits.csv"):
    """Merge rows into credits.csv keyed by file, so reruns do not duplicate."""
    existing = {}
    if Path(path).exists():
        with open(path, newline="") as f:
            existing = {r["file"]: r for r in csv.DictReader(f)}
    existing.update({r["file"]: r for r in rows})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, CREDIT_FIELDS)
        w.writeheader()
        w.writerows(sorted(existing.values(), key=lambda r: r["file"]))


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "SuoKuulo/0.1 (Junction 2026)", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def search(sci, extra, key):
    q = urllib.parse.urlencode({"query": f'sp:"{sci}" {extra}', "key": key})
    return json.loads(get(f"{API}?{q}"))["recordings"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-species", type=int, default=10)
    ap.add_argument("--species", default="config/species.yaml")
    args = ap.parse_args()
    key = os.environ.get("XC_API_KEY") or sys.exit("set XC_API_KEY (https://xeno-canto.org/account)")

    for s in load_species(args.species):
        if s.kind != "indicator":
            continue
        sci = s.label.split("_")[0]
        picked = {}
        for extra in QUERIES:
            for r in search(sci, extra, key):
                if len(picked) < args.per_species and r["id"] not in picked:
                    picked[r["id"]] = r
            if len(picked) >= args.per_species:
                break
        out = Path("test_clips") / s.id
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for r in picked.values():
            path = out / f"XC{r['id']}{Path(r['file-name']).suffix.lower() or '.mp3'}"
            if not path.exists():
                path.write_bytes(get(r["file"]))
            rows.append({"file": str(path), "label": s.id, "source": "xeno-canto",
                         "recordist": r["rec"], "licence": r["lic"], "url": r["url"]})
        update_credits(rows)
        print(f"{s.id:15s} {len(rows):2d} clips ({sci})")


if __name__ == "__main__":
    main()
