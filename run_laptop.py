"""Laptop entrypoint. See README.md for the commands."""
import argparse
import sys

import numpy as np

from suokuulo import config
from suokuulo.audio import WINDOW, make_source
from suokuulo.classifier import MockClassifier
from suokuulo.display import ConsoleDisplay
from suokuulo.eventlog import EventLog
from suokuulo.pipeline import Pipeline, simulated
from suokuulo.state import State
from suokuulo.web.server import serve

# --mock: one list of (label, confidence) per 3 s window. Score rises, then an
# engine trips the alarm, which clears 20 s after the last engine hit.
MOCK_SCRIPT = [
    [], [], [],
    [("golden_plover", 0.81)], [("golden_plover", 0.77)],
    [("common_snipe", 0.66)], [], [("common_snipe", 0.58)],
    [("engine", 0.30)],                       # below threshold, not a hit
    [("engine", 0.62)], [("engine", 0.71)],
    [], [], [], [], [], [], [], [], [],
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/laptop.yaml")
    ap.add_argument("--mock", action="store_true", help="scripted detections, no model, no audio")
    ap.add_argument("--input", help="override audio file/folder")
    ap.add_argument("--realtime", action="store_true", help="pace file replay at one window per 3 s")
    ap.add_argument("--loop", action="store_true", help="loop file replay forever")
    ap.add_argument("--mic", nargs="?", const="mic", choices=["mic", "arecord"],
                    help="live capture: sounddevice (default) or arecord")
    ap.add_argument("--device", help="mic device (sounddevice index/name, or ALSA name for arecord)")
    ap.add_argument("--mute", action="store_true", help="buzzer off")
    ap.add_argument("--no-web", action="store_true", help="do not start the dashboard")
    ap.add_argument("-v", "--verbose", action="store_true", help="print raw detections per window")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # live console when piped to a file

    cfg = config.load(args.config)
    cfg.mute |= args.mute
    species = config.load_species(cfg.species_file)
    display = ConsoleDisplay(species)

    if args.mock:
        windows, now = simulated(np.zeros(WINDOW, np.float32) for _ in MOCK_SCRIPT)
        Pipeline(cfg, species, MockClassifier(MOCK_SCRIPT, species), display, now=now,
                 log=EventLog(cfg.log_file)).run(windows, mute=cfg.mute)
        return

    if args.input:
        cfg.source, cfg.input = "file", args.input
    if args.mic:
        cfg.source = args.mic
    if args.device:
        cfg.device = int(args.device) if args.device.isdigit() else args.device
    cfg.realtime |= args.realtime
    cfg.loop |= args.loop
    from suokuulo.classifier import BirdNetClassifier
    classifier = BirdNetClassifier(species, cfg.min_conf)
    state = None if args.no_web else State()
    if state:
        serve(state, cfg.web_host, cfg.web_port)
    Pipeline(cfg, species, classifier, display, state=state, log=EventLog(cfg.log_file),
             verbose=args.verbose).run(make_source(cfg).windows(), mute=cfg.mute)


if __name__ == "__main__":
    main()
