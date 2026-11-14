"""Feed the demo playlist (`demo` in the config: quiet, birds) through the full
pipeline at full speed with a simulated clock and print health over time, to check the demo behaves sensibly
before running it live. Same classifier, smoother and scoring as the board.

Usage: python scripts/simulate.py [--config config/laptop.yaml] [--start 2026-06-10T05:00] [--web]
--start: local time the simulated clock starts at (default: now). It picks
dawn/day/night expectations, and the season unless the config fixes it.
--web: serve the dashboard on the config's web_port while and after it runs.
"""
import argparse
import itertools
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from suokuulo import config  # noqa: E402
from suokuulo.audio import FileSource  # noqa: E402
from suokuulo.classifier import BirdNetClassifier  # noqa: E402
from suokuulo.pipeline import Pipeline  # noqa: E402
from suokuulo.state import State  # noqa: E402
from suokuulo.web.server import serve  # noqa: E402


class Quiet:
    """Display that records instead of printing."""

    def __init__(self):
        self.sounds = []

    def show_score(self, score):
        pass

    def beep(self):
        self.sounds.append("beep")

    def heartbeat(self):
        pass

    def uplink(self, *summary):
        self.sounds.append(f"uplink {summary}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/laptop.yaml")
    ap.add_argument("--start", help="local ISO time, e.g. 2026-06-10T05:00 (default: now)")
    ap.add_argument("--web", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # live timeline when piped
    cfg = config.load(args.config)
    tz = ZoneInfo(cfg.timezone)
    clock = [datetime.fromisoformat(args.start).replace(tzinfo=tz).timestamp() if args.start else time.time()]
    species = config.active_species(cfg)
    display, state = Quiet(), State(cfg.site_name, tz) if args.web else None
    if state:
        serve(state, cfg.web_host, cfg.web_port)
    pipeline = Pipeline(cfg, species, BirdNetClassifier(species, cfg.min_conf, cfg.highpass_hz), display,
                        now=lambda: clock[0], state=state)
    pipeline.run([])  # startup: beep, first score

    start, last = clock[0], None
    print(f"start {datetime.fromtimestamp(start, tz):%Y-%m-%d %H:%M} {cfg.timezone}, "
          f"profile {pipeline.soundscape.health()['profile']}, window {cfg.score_window_min} min, hop {cfg.hop_s} s\n")
    print(" time  segment                      health          richness activity  events")
    for path, n in cfg.demo:
        segment = Path(path).name + ("/" if Path(path).is_dir() else "")
        for w in itertools.islice(FileSource(path, hop_s=cfg.hop_s).windows(), n):
            events = pipeline.step(w)
            h = pipeline.soundscape.health()
            row = h["score"]
            if events or row != last:
                last = row
                pct = lambda x: "--" if x is None else f"{100 * x:3.0f}%"  # noqa: E731
                names = ", ".join(f"{e.label} {e.confidence:.2f}" for e in events)
                m, s = divmod(int(clock[0] - start), 60)
                print(f"{m:2d}:{s:02d}  {segment[:28]:28s} {str(h['score']):>3} {h['label']:10s}  "
                      f"{pct(h['richness']):>8} {pct(h['activity']):>8}  {names}")
            clock[0] += cfg.hop_s

    snap = pipeline.soundscape.snapshot()
    heard = [r["common"] for r in snap["species"] if r["detections_today"]]
    print(f"\nend: health {snap['health']['score']} ({snap['health']['label']}), species heard: {', '.join(heard) or 'none'}")
    print(f"     buzzer: {', '.join(display.sounds)}")
    if args.web:
        print(f"\ndashboard on http://localhost:{cfg.web_port}/ (Ctrl-C to stop)")
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()
