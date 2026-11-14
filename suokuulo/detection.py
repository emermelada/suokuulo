"""Per-label smoothing: k hits in the last n windows (or one strong window)
confirms, then a cooldown. The first confirmation of a label is never delayed."""
import time
from collections import deque

from .classifier import Detection
from .config import VOICE


POOL = "any_disturbance"


class Smoother:
    def __init__(self, cfg, now=time.monotonic):
        self.now = now
        self.threshold = {"indicator": cfg.indicator_hit, "disturbance": cfg.disturbance_hit}
        self.label_hit = cfg.species_hit or {}
        self.pool_hit = cfg.any_disturbance_hit
        self.n, self.k, self.cooldown = cfg.hit_window, cfg.hits_needed, cfg.cooldown_s
        self.single = cfg.confirm_single or float("inf")
        self.label_single = cfg.species_single or {}
        self.history = {}   # key -> deque of the hit Detection per window, None = miss
        self.last = {}      # key -> time of last confirmation
        self.hits = []      # detections that counted as hits in the latest window

    def key(self, d):
        """Smoothing key: the label, or POOL for machinery/gun when pooling is on."""
        pooled = self.pool_hit is not None and d.kind == "disturbance" and d.label != VOICE
        return POOL if pooled else d.label

    def hit_threshold(self, key, d):
        return self.pool_hit if key == POOL else self.label_hit.get(d.label, self.threshold[d.kind])

    def update(self, detections: list[Detection]) -> list[Detection]:
        """Feed one window's detections, return newly confirmed events.

        Every label is judged on its own (a disturbance never hides a bird in
        the same window). A pooled event carries the strongest label in it.
        """
        t = self.now()
        best = {}
        for d in detections:
            k = self.key(d)
            if d.confidence >= self.hit_threshold(k, d) and d.confidence > getattr(best.get(k), "confidence", 0):
                best[k] = d
        self.hits = list(best.values())
        for k in best:
            self.history.setdefault(k, deque(maxlen=self.n))
        events = []
        for k, h in self.history.items():
            h.append(best.get(k))
            hits = [d for d in h if d]
            strong = k in best and best[k].confidence >= self.label_single.get(k, self.single)
            if (len(hits) >= self.k or strong) and t - self.last.get(k, -1e18) >= self.cooldown:
                self.last[k] = t
                events.append(max(hits, key=lambda d: d.confidence))
        return events
