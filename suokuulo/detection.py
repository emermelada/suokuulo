"""Per-label smoothing: k hits in the last n windows confirms, then a cooldown."""
import time
from collections import deque

from .classifier import Detection


class Smoother:
    def __init__(self, cfg, now=time.monotonic):
        self.now = now
        self.threshold = {"indicator": cfg.indicator_hit, "disturbance": cfg.disturbance_hit}
        self.n, self.k, self.cooldown = cfg.hit_window, cfg.hits_needed, cfg.cooldown_s
        self.history = {}   # label -> deque of hit confidences, 0.0 = miss
        self.kind = {}
        self.last = {}      # label -> time of last confirmation
        self.hits = []      # detections that counted as hits in the latest window

    def update(self, detections: list[Detection]) -> list[Detection]:
        """Feed one window's detections, return newly confirmed events."""
        t = self.now()
        best = {}
        for d in detections:
            if d.confidence >= self.threshold[d.kind] and d.confidence > getattr(best.get(d.label), "confidence", 0):
                best[d.label] = d
        self.hits = list(best.values())
        for d in self.hits:
            self.history.setdefault(d.label, deque(maxlen=self.n))
            self.kind[d.label] = d.kind
        events = []
        for label, h in self.history.items():
            h.append(best[label].confidence if label in best else 0.0)
            if sum(c > 0 for c in h) >= self.k and t - self.last.get(label, -1e18) >= self.cooldown:
                self.last[label] = t
                events.append(Detection(label, self.kind[label], max(h)))
        return events
