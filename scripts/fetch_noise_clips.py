"""Download ESC-50 clips (karolpiczak/ESC-50, CC BY-NC 3.0) for disturbance
tests and demo background, with per-clip attribution parsed from its LICENSE.

    chainsaw -> test_clips/power_tools/
    engine   -> test_clips/engine/
    wind     -> test_clips/background/   (demo filler, not a label)

Usage: python scripts/fetch_noise_clips.py [--per-class 10]
"""
import argparse
import csv
import io
import re
from pathlib import Path

from fetch_bird_clips import get, update_credits

RAW = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master"
CLASSES = {"chainsaw": "power_tools", "engine": "engine", "wind": "background"}
# "- [1-116765-A.ogg]: clip derived from chainsaw.wav (http://...) by UncleSigmund [CC0]"
ATTRIBUTION = re.compile(r"^- \[(\S+)\.ogg\]: .* \((http\S+)\) by (.+) \[([^\]]+)\]$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=10)
    args = ap.parse_args()

    meta = list(csv.DictReader(io.StringIO(get(f"{RAW}/meta/esc50.csv").decode())))
    attribution = {m[1]: m.groups()[1:] for line in get(f"{RAW}/LICENSE").decode().splitlines()
                   if (m := ATTRIBUTION.match(line))}
    for category, label in CLASSES.items():
        out = Path("test_clips") / label
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for m in [m for m in meta if m["category"] == category][:args.per_class]:
            path = out / f"ESC50-{m['filename']}"
            if not path.exists():
                path.write_bytes(get(f"{RAW}/audio/{m['filename']}"))
            url, recordist, lic = attribution.get(m["filename"].rsplit("-", 1)[0], ("", "unknown", ""))
            rows.append({"file": str(path), "label": label, "source": "ESC-50 (CC BY-NC 3.0)",
                         "recordist": recordist, "licence": lic, "url": url})
        update_credits(rows)
        print(f"{category:9s} -> {label:12s} {len(rows):2d} clips")


if __name__ == "__main__":
    main()
