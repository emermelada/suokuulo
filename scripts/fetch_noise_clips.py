"""Download machinery and background clips for disturbance tests, the demo and
false-alarm measurement, credited in credits.csv.

ESC-50 (karolpiczak/ESC-50, CC BY-NC 3.0), attribution parsed from its LICENSE:
    chainsaw -> test_clips/power_tools/
    engine   -> test_clips/engine/
    wind     -> test_clips/background/   (negatives + demo filler)

--frugalai: Rainforest Connection rfcx/frugalai on Hugging Face (CC BY-NC 4.0),
3 s clips. Gated: log in, accept the terms on the dataset page, then set
HF_TOKEN (https://huggingface.co/settings/tokens). Never commit it.
    chainsaw    -> test_clips/power_tools/
    environment -> test_clips/background/

--speech: read speech from LibriSpeech dev-clean (CC BY 4.0, openslr.org/12)
via the public openslr/librispeech_asr dataset, rows spread over the split so
each clip is a different speaker. For the human_voice label and the bird+speech
mix in tests and scripts/evaluate.py --mix.
    speech      -> test_clips/human_voice/

Usage: python scripts/fetch_noise_clips.py [--per-class 10] [--frugalai 20] [--speech 10]
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from fetch_bird_clips import get, update_credits

RAW = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master"
CLASSES = {"chainsaw": "power_tools", "engine": "engine", "wind": "background"}
# "- [1-116765-A.ogg]: clip derived from chainsaw.wav (http://...) by UncleSigmund [CC0]"
ATTRIBUTION = re.compile(r"^- \[(\S+)\.ogg\]: .* \((http\S+)\) by (.+) \[([^\]]+)\]$")
FRUGALAI = {0: "power_tools", 1: "background"}  # dataset class ids: 0 chainsaw, 1 environment


def fetch_esc50(per_class):
    meta = list(csv.DictReader(io.StringIO(get(f"{RAW}/meta/esc50.csv").decode())))
    attribution = {m[1]: m.groups()[1:] for line in get(f"{RAW}/LICENSE").decode().splitlines()
                   if (m := ATTRIBUTION.match(line))}
    for category, label in CLASSES.items():
        out = Path("test_clips") / label
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for m in [m for m in meta if m["category"] == category][:per_class]:
            path = out / f"ESC50-{m['filename']}"
            if not path.exists():
                path.write_bytes(get(f"{RAW}/audio/{m['filename']}"))
            url, recordist, lic = attribution.get(m["filename"].rsplit("-", 1)[0], ("", "unknown", ""))
            rows.append({"file": str(path), "label": label, "source": "ESC-50 (CC BY-NC 3.0)",
                         "recordist": recordist, "licence": lic, "url": url})
        update_credits(rows)
        print(f"ESC-50   {category:11s} -> {label:12s} {len(rows):2d} clips")


def fetch_frugalai(n):
    token = os.environ.get("HF_TOKEN") or sys.exit("set HF_TOKEN (dataset is gated, accept its terms first)")
    auth = {"Authorization": f"Bearer {token}"}
    # /filter needs the search index, which this dataset lacks; page /rows (max 100) instead.
    picked, offset = {c: [] for c in FRUGALAI}, 0
    while any(len(v) < n for v in picked.values()) and offset < 2000:
        q = urllib.parse.urlencode({"dataset": "rfcx/frugalai", "config": "default", "split": "test",
                                    "offset": offset, "length": 100})
        for r in json.loads(get(f"https://datasets-server.huggingface.co/rows?{q}", auth))["rows"]:
            if len(picked[r["row"]["label"]]) < n:
                picked[r["row"]["label"]].append(r)
        offset += 100
    for class_id, label in FRUGALAI.items():
        rows = []
        out = Path("test_clips") / label
        out.mkdir(parents=True, exist_ok=True)
        for r in picked[class_id]:
            path = out / f"FRUGALAI-test-{r['row_idx']}.wav"
            if not path.exists():
                path.write_bytes(get(r["row"]["audio"][0]["src"], auth))
            rows.append({"file": str(path), "label": label, "source": "rfcx/frugalai (CC BY-NC 4.0)",
                         "recordist": "Rainforest Connection", "licence": "CC BY-NC 4.0",
                         "url": f"https://huggingface.co/datasets/rfcx/frugalai (test row {r['row_idx']})"})
        update_credits(rows)
        print(f"frugalai class {class_id} -> {label:12s} {len(rows):2d} clips")


def fetch_speech(n, rows_in_split=2703):
    out = Path("test_clips/human_voice")
    out.mkdir(parents=True, exist_ok=True)
    credits = []
    for offset in range(0, rows_in_split, rows_in_split // n)[:n]:
        q = urllib.parse.urlencode({"dataset": "openslr/librispeech_asr", "config": "clean", "split": "validation",
                                    "offset": offset, "length": 1})
        row = json.loads(get(f"https://datasets-server.huggingface.co/rows?{q}"))["rows"][0]["row"]
        path = out / f"LIBRISPEECH-{row['id']}.flac"
        if not path.exists():
            path.write_bytes(get(row["audio"][0]["src"]))
        credits.append({"file": str(path), "label": "human_voice", "source": "LibriSpeech dev-clean (CC BY 4.0)",
                        "recordist": f"LibriVox reader, speaker {row['speaker_id']}", "licence": "CC BY 4.0",
                        "url": "https://www.openslr.org/12"})
    update_credits(credits)
    print(f"LibriSpeech speech -> human_voice  {len(credits):2d} clips")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=10, help="ESC-50 clips per class")
    ap.add_argument("--frugalai", type=int, default=0, metavar="N", help="also fetch N rfcx/frugalai clips per label")
    ap.add_argument("--speech", type=int, default=0, metavar="N", help="also fetch N LibriSpeech speech clips")
    args = ap.parse_args()
    fetch_esc50(args.per_class)
    if args.frugalai:
        fetch_frugalai(args.frugalai)
    if args.speech:
        fetch_speech(args.speech)


if __name__ == "__main__":
    main()
