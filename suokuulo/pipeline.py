"""Main loop: audio window -> classifier -> smoother -> score -> display/log/state."""
import time
from datetime import datetime

from .detection import Smoother
from .scoring import ScoreEngine

SAMPLE_RATE = 48000


class Pipeline:
    def __init__(self, cfg, species, classifier, display, now=time.monotonic, state=None, log=None, verbose=False):
        self.classifier, self.display, self.state, self.log = classifier, display, state, log
        self.verbose = verbose
        self.index = {s.id: i for i, s in enumerate(species)}
        self.smoother = Smoother(cfg, now)
        self.scorer = ScoreEngine(cfg, {s.id: s.weight for s in species if s.kind == "indicator"}, now)
        self.windows = 0
        self.inference_ms = []  # last 20 windows

    def step(self, window, sample_rate=SAMPLE_RATE):
        t0 = time.perf_counter()
        detections = self.classifier.classify(window, sample_rate)
        inference_ms = (time.perf_counter() - t0) * 1000
        self.windows += 1
        self.inference_ms = (self.inference_ms + [inference_ms])[-20:]
        if self.windows % 20 == 0:
            print(f"[timing] mean inference {sum(self.inference_ms) / 20:.0f} ms/window over last 20 windows")
        if self.verbose:
            raw = ", ".join(f"{d.label} {d.confidence:.2f}" for d in sorted(detections, key=lambda d: -d.confidence))
            print(f"  window {self.windows:4d} {inference_ms:5.0f} ms  {raw or '-'}")

        events = self.smoother.update(detections)
        disturbance_hit = any(d.kind == "disturbance" for d in self.smoother.hits)
        prev_score, prev_alarm = self.scorer.score, self.scorer.alarm
        alerts = self.scorer.update(events, disturbance_hit)
        score, now_iso = self.scorer.score, datetime.now().isoformat(timespec="seconds")

        for e in events:
            print(f"{now_iso} window {self.windows:4d} EVENT {e.label} ({e.kind}) conf {e.confidence:.2f} score {score}")
            if e.kind == "indicator":
                self.display.show_bird(self.index[e.label])
        for a in alerts:
            print(f"{now_iso} window {self.windows:4d} ALERT {a['type']} {a['label']}")
        if score != prev_score:
            self.display.show_score(score)
        if self.scorer.alarm != prev_alarm:
            self.display.alarm(self.scorer.alarm)

        if self.log:
            alert = ";".join(a["type"] for a in alerts)
            for e in events:
                self.log.write(now_iso, e, score, alert)
        if self.state:
            self.state.update(now_iso, events, alerts, score, self.scorer.alarm,
                              self.scorer.species_heard(), inference_ms)
        return events

    def run(self, windows):
        self.display.show_score(self.scorer.score)
        for w in windows:
            self.step(w)


def simulated(windows, step_s=3.0):
    """Wrap a window iterator with a fake clock that advances step_s per window.

    Returns (windows, now). Lets replays and evaluation run at full speed while
    cooldowns and expiry still see audio time.
    """
    clock = [0.0]

    def gen():
        for w in windows:
            yield w
            clock[0] += step_s

    return gen(), lambda: clock[0]
