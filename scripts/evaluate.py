"""Run every clip in test_clips/<label>/ through BirdNET + the smoother and
write <out>.md and <out>.csv (default eval_results).

A clip is a hit if its label is confirmed at least once. Each clip gets a fresh
smoother and a simulated clock, so results do not depend on clip order or wall
time. Folders that are not a species id (background/) are negatives. Detection
settings come from --config (laptop.yaml includes board.yaml, so these are the
board's settings).

Modes:
  --speech DIR   overlay a speech clip from DIR on every bird clip (equal RMS)
  --mixed        overlay every pair of indicator species (equal RMS) and compare
                 each bird's confidence alone vs in the mix
  --set K=V      override a config key (YAML value), e.g. --set highpass_hz=0
  --compare NAME=CSV  add a column per earlier run's CSV to the comparison table

Usage: python scripts/evaluate.py [--config config/laptop.yaml] [--out eval_results]
"""
import argparse
import csv
import itertools
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from suokuulo import config  # noqa: E402
from suokuulo.audio import SAMPLE_RATE, audio_files, load_audio, split_windows  # noqa: E402
from suokuulo.classifier import BirdNetClassifier  # noqa: E402
from suokuulo.config import VOICE  # noqa: E402
from suokuulo.detection import Smoother  # noqa: E402
from suokuulo.pipeline import simulated  # noqa: E402

SEGMENT_S = 15  # --mixed: length of each bird's segment


def run_audio(y, classifier, cfg, timings):
    """One clip through the classifier and a fresh smoother."""
    hop = int(cfg.hop_s * SAMPLE_RATE)
    windows, now = simulated(split_windows(y, hop), step_s=cfg.hop_s)
    smoother = Smoother(cfg, now)
    r = {"windows": 0, "confirmed": set(), "hit_windows": Counter(), "first_s": {},
         "max_conf": defaultdict(float), "per_window": []}
    for w in windows:
        t0 = time.perf_counter()
        detections = classifier.classify(w, SAMPLE_RATE)
        timings.append(time.perf_counter() - t0)
        for d in detections:
            r["max_conf"][d.label] = max(r["max_conf"][d.label], d.confidence)
        r["per_window"].append({d.label: d.confidence for d in detections})
        for e in smoother.update(detections):
            r["confirmed"].add(e.label)
            r["first_s"].setdefault(e.label, now() + 3.0)  # seconds of audio heard when it fired
        r["hit_windows"].update(d.label for d in smoother.hits)
        r["windows"] += 1
    return r


def rms_scaled(y, rms=0.05):
    return y * (rms / max(float(np.sqrt(np.mean(y ** 2))), 1e-9))


def tiled(y, n):
    return np.tile(y, -(-n // len(y)))[:n]


def source(path):
    name = Path(path).name
    return {"ESC50": "ESC-50", "FRUGALAI": "frugalai", "LIBRISPEECH": "LibriSpeech"}.get(name.split("-")[0], "xeno-canto")


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def split(s):
    return set(filter(None, s.split(";")))


def summary(rows, kind):
    """Clip-level metrics from eval rows (in memory or read back from a CSV)."""
    machinery = {l for l, k in kind.items() if k == "disturbance" and l != VOICE}
    indicators = sorted(l for l, k in kind.items() if k == "indicator")
    m = {}
    for label in indicators:
        rs = [r for r in rows if r["label"] == label]
        m[f"{label} clips confirmed"] = f"{sum(label in split(r['confirmed']) for r in rs)}/{len(rs)}"
    birds = [r for r in rows if r["label"] in indicators]
    m["bird clips confirmed (all species)"] = pct(sum(r["label"] in split(r["confirmed"]) for r in birds), len(birds))
    firsts = [float(r["first_s"]) for r in birds if r.get("first_s")]
    m["median s of audio to first bird event"] = f"{statistics.median(firsts):.0f}" if firsts else "-"
    m["clips confirming a wrong indicator"] = sum(bool(split(r["confirmed"]) & (set(indicators) - {r["label"]})) for r in rows)
    m["golden_plover confirmed on other clips"] = sum("golden_plover" in split(r["confirmed"]) for r in rows
                                                      if r["label"] != "golden_plover")
    tp, n = Counter(), Counter()
    for r in rows:
        if r["label"] in machinery:
            group = f"{r['label']} {source(r['file'])}"
            n[group] += 1
            tp[group] += bool(split(r["confirmed"]) & machinery)
    for group in sorted(n):
        m[f"machinery recall, {group} clips"] = f"{tp[group]}/{n[group]} ({pct(tp[group], n[group])})"
    esc = sum(v for g, v in tp.items() if g.endswith("ESC-50"))
    m["machinery recall, all ESC-50 clips"] = f"{esc}/{sum(v for g, v in n.items() if g.endswith('ESC-50'))}"
    fp_bg = sum(bool(split(r["confirmed"]) & machinery) for r in rows if r["label"] not in kind)
    fp_all = sum(bool(split(r["confirmed"]) & machinery) for r in rows if r["label"] not in machinery)
    m["machinery false alarms, background clips"] = fp_bg
    m["machinery false alarms, bird + speech clips"] = fp_all - fp_bg
    m["machinery precision vs background (ESC-50)"] = pct(esc, esc + fp_bg)
    m["machinery precision vs all non-machinery clips"] = pct(sum(tp.values()), sum(tp.values()) + fp_all)
    voice = [r for r in rows if r["label"] == VOICE]
    m["human_voice confirmed on speech clips"] = f"{sum(VOICE in split(r['confirmed']) for r in voice)}/{len(voice)}"
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/laptop.yaml")
    ap.add_argument("--clips", default="test_clips")
    ap.add_argument("--out", default="eval_results")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    ap.add_argument("--speech", metavar="DIR", help="overlay speech from DIR on every bird clip")
    ap.add_argument("--mixed", action="store_true", help="overlay every pair of indicator species")
    ap.add_argument("--compare", nargs="*", default=[], metavar="NAME=CSV")
    args = ap.parse_args()
    cfg = config.load(args.config)
    for kv in args.set:
        k, v = kv.split("=", 1)
        if not hasattr(cfg, k):
            sys.exit(f"unknown config key {k}")
        setattr(cfg, k, yaml.safe_load(v))
    species = config.load_species(cfg.species_file)
    kind = {s.id: s.kind for s in species}
    classifier = BirdNetClassifier(species, cfg.min_conf, cfg.highpass_hz)
    speech = audio_files(args.speech) if args.speech else []

    timings, rows, best = [], [], {}
    for folder in sorted(p for p in Path(args.clips).iterdir() if p.is_dir()):
        for i, f in enumerate(audio_files(folder)):
            y, mix = load_audio(f), ""
            if speech and kind.get(folder.name) == "indicator":
                s = speech[i % len(speech)]
                y, mix = rms_scaled(y) + rms_scaled(tiled(load_audio(s), len(y))), s.name
            r = run_audio(y, classifier, cfg, timings)
            target = {folder.name} if kind.get(folder.name) != "disturbance" or folder.name == VOICE else \
                {l for l, k in kind.items() if k == "disturbance" and l != VOICE}
            firsts = [r["first_s"][l] for l in target if l in r["first_s"]]
            rows.append({"file": str(f), "label": folder.name, "mix": mix, "windows": r["windows"],
                         "confirmed": ";".join(sorted(r["confirmed"])),
                         "target_hit_windows": r["hit_windows"].get(folder.name, 0),
                         "disturbance_hit_windows": sum(v for k, v in r["hit_windows"].items() if kind[k] == "disturbance"),
                         "first_s": f"{min(firsts):.0f}" if firsts else "",
                         "max_conf": ";".join(f"{k}={v:.2f}" for k, v in sorted(r["max_conf"].items()))})
            if kind.get(folder.name) == "indicator" and not mix:
                score = (r["hit_windows"].get(folder.name, 0), r["max_conf"].get(folder.name, 0))
                if score > best.get(folder.name, ((-1, 0), None))[0]:
                    best[folder.name] = (score, f, r["per_window"])
        print(f"{folder.name:15s} done")

    with open(f"{args.out}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by_label = defaultdict(list)
    for r in rows:
        by_label[r["label"], source(r["file"])].append(r)
    pos = ["| label | source | clips | hits | misses | hit rate | window hit rate | any-disturbance window rate |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    neg = ["| folder | source | clips | windows | clips with disturbance alarm | clips with indicator confirmed | disturbance window false-hit rate |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for (label, src), rs in by_label.items():
        windows = sum(r["windows"] for r in rs)
        dist_windows = sum(r["disturbance_hit_windows"] for r in rs)
        if label in kind:
            hits = sum(label in split(r["confirmed"]) for r in rs)
            target_windows = sum(r["target_hit_windows"] for r in rs)
            pos.append(f"| {label} | {src} | {len(rs)} | {hits} | {len(rs) - hits} | {pct(hits, len(rs))} "
                       f"| {pct(target_windows, windows)} | {pct(dist_windows, windows)} |")
        else:
            confirmed = [split(r["confirmed"]) for r in rs]
            alarms = sum(any(kind[l] == "disturbance" for l in c) for c in confirmed)
            birds = sum(any(kind[l] == "indicator" for l in c) for c in confirmed)
            neg.append(f"| {label} | {src} | {len(rs)} | {windows} | {alarms} | {birds} | {pct(dist_windows, windows)} |")

    # Highest window score each indicator reached on clips of other folders: the
    # margin under its threshold (golden_plover has weight 3, so it matters most).
    margin = ["| label | threshold | clips of other folders confirming it | highest window score on other folders |",
              "| --- | --- | --- | --- |"]
    for label in sorted(l for l, k in kind.items() if k == "indicator"):
        others = [r for r in rows if r["label"] != label]
        top = max((float(v) for r in others for kv in r["max_conf"].split(";") if kv
                   for k, v in [kv.split("=")] if k == label), default=0.0)
        threshold = (cfg.species_hit or {}).get(label, cfg.indicator_hit)
        margin.append(f"| {label} | {threshold} | {sum(label in split(r['confirmed']) for r in others)} | {top:.2f} |")

    sections = []
    if args.mixed:
        sections.append(mixed_report(best, classifier, cfg, timings))
    columns = {name: list(csv.DictReader(open(path))) for name, path in (c.split("=", 1) for c in args.compare)}
    columns["this run"] = rows
    sums = {name: summary(rs, kind) for name, rs in columns.items()}
    comparison = ["| metric | " + " | ".join(sums) + " |", "| --- |" + " --- |" * len(sums)]
    for metric in sums["this run"]:
        comparison.append(f"| {metric} | " + " | ".join(str(s.get(metric, "-")) for s in sums.values()) + " |")

    mean_ms = 1000 * sum(timings) / len(timings)
    overrides = f" Overrides: `{' '.join(args.set)}`." if args.set else ""
    mixing = f" Every bird clip overlaid with speech from `{args.speech}` at equal RMS." if speech else ""
    report = f"""# SuoKuulo evaluation

Generated by `python scripts/evaluate.py {' '.join(sys.argv[1:])}` on {time.strftime('%Y-%m-%d %H:%M')}.
BirdNET v2.4 TFLite model (files from birdnetlib), run directly with ai-edge-litert. Settings from
`{args.config}`:{overrides}{mixing}
3 s windows every {cfg.hop_s} s; high-pass {cfg.highpass_hz or 'off'} Hz; indicator threshold
{cfg.indicator_hit} (overrides {cfg.species_hit or 'none'}); any-disturbance threshold
{cfg.any_disturbance_hit or 'off'}, human voice {cfg.disturbance_hit}; confirm {cfg.hits_needed} of
{cfg.hit_window} windows or one window >= {cfg.confirm_single} (overrides {cfg.species_single or 'none'}).

- Model imports + load: {classifier.load_s:.2f} s
- Mean inference: {mean_ms:.0f} ms per window over {len(timings)} windows (this machine)

## Comparison

Clip-level. Machinery = every disturbance label except human voice, pooled
into one any-disturbance signal. First-event time counts seconds of audio
heard when the event fired (before-runs without that column show -).

{chr(10).join(comparison)}

## Positives

A clip is a hit if its label is confirmed at least once. Window hit rate is the
share of windows where the label scored at or above its threshold.
Any-disturbance window rate counts windows where any disturbance label hit.

{chr(10).join(pos)}

## Negatives (false alarms)

{chr(10).join(neg)}

## Indicator false confirmations

{chr(10).join(margin)}
{chr(10).join(sections)}
## Caveats

- Clips of 3 s or less (rfcx/frugalai) are a single window: they can only
  confirm through the single-window rule.
- Xeno-canto clips are mostly short, focal recordings; a field microphone on a
  bog will hear birds further away and quieter.
- Per-clip detail: {args.out}.csv.
"""
    Path(f"{args.out}.md").write_text(report)
    print(report)


def mixed_report(best, classifier, cfg, timings):
    """Overlay every pair of indicator species at equal RMS: each species' best
    clip (most hit windows alone), the SEGMENT_S seconds around its strongest window."""
    hop, n = int(cfg.hop_s * SAMPLE_RATE), SEGMENT_S * SAMPLE_RATE
    segment = {}
    for label, (_, f, per_window) in best.items():
        y = load_audio(f)
        peak = max(range(len(per_window)), key=lambda i: per_window[i].get(label, 0))
        start = max(0, min(peak * hop - 6 * SAMPLE_RATE, len(y) - n))
        segment[label] = rms_scaled(tiled(y[start:start + n], n))
    alone = {label: run_audio(y, classifier, cfg, timings) for label, y in segment.items()}
    lines = ["| pair | A conf alone -> mixed | B conf alone -> mixed | A confirmed | B confirmed |",
             "| --- | --- | --- | --- | --- |"]
    drops, both = [], 0
    for a, b in itertools.combinations(sorted(segment), 2):
        r = run_audio(segment[a] + segment[b], classifier, cfg, timings)
        cells = []
        for label in (a, b):
            c0, c1 = alone[label]["max_conf"].get(label, 0), r["max_conf"].get(label, 0)
            drops.append(c0 - c1)
            cells.append(f"{c0:.2f} -> {c1:.2f}")
        ok = [label in r["confirmed"] for label in (a, b)]
        both += all(ok)
        lines.append(f"| {a} + {b} | {cells[0]} | {cells[1]} | {'yes' if ok[0] else 'no'} | {'yes' if ok[1] else 'no'} |")
    pairs = len(lines) - 2
    clips = ", ".join(f"{label} {Path(f).name}" for label, (_, f, _) in sorted(best.items()))
    return f"""
## Simultaneous species (--mixed)

Every pair of indicator species overlaid at equal RMS, {SEGMENT_S} s each. Clips: {clips}.
Confidence is the label's highest window score; "alone" is the same segment
at the same level without the other bird.

- Both species confirmed in {both} of {pairs} pairs
- Mean confidence drop in the mix: {statistics.mean(drops):.2f} (median {statistics.median(drops):.2f}, max {max(drops):.2f})

{chr(10).join(lines)}
"""


if __name__ == "__main__":
    main()
