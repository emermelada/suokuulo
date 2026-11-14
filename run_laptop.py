"""Laptop entrypoint. See README.md for the commands."""
import argparse

import numpy as np

from suokuulo import config
from suokuulo.audio import WINDOW, make_source
from suokuulo.classifier import MockClassifier
from suokuulo.display import ConsoleDisplay
from suokuulo.eventlog import EventLog
from suokuulo.pipeline import Pipeline, simulated

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
    ap.add_argument("-v", "--verbose", action="store_true", help="print raw detections per window")
    args = ap.parse_args()

    cfg = config.load(args.config)
    species = config.load_species(cfg.species_file)
    display = ConsoleDisplay(species)

    if args.mock:
        windows, now = simulated(np.zeros(WINDOW, np.float32) for _ in MOCK_SCRIPT)
        Pipeline(cfg, species, MockClassifier(MOCK_SCRIPT, species), display, now=now,
                 log=EventLog(cfg.log_file)).run(windows)
        return

    if args.input:
        cfg.source, cfg.input = "file", args.input
    from suokuulo.classifier import BirdNetClassifier
    classifier = BirdNetClassifier(species, cfg.min_conf)
    Pipeline(cfg, species, classifier, display, log=EventLog(cfg.log_file), verbose=args.verbose).run(make_source(cfg).windows())


if __name__ == "__main__":
    main()
