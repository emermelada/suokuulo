"""Soundscape health score and alerts, section 7 of the brief."""
import time


class ScoreEngine:
    def __init__(self, cfg, weights: dict[str, int], now=time.monotonic):
        self.cfg, self.weights, self.now = cfg, weights, now
        self.indicators = []     # (time, label) of indicator events
        self.disturbances = []   # (time, label) of disturbance events
        self.last_disturbance_hit = None
        self.last_event = now()
        self.alarm = False
        self.silent = False
        self.score = cfg.base_score

    def update(self, events, disturbance_hit=False) -> list[dict]:
        """Feed one window's confirmed events; return new alerts as {type, label}."""
        c, t = self.cfg, self.now()
        alerts = []
        for e in events:
            if e.kind == "indicator":
                self.indicators.append((t, e.label))
            else:
                self.disturbances.append((t, e.label))
                alerts.append({"type": "disturbance", "label": e.label})
                self.alarm = True
        if disturbance_hit or any(e.kind == "disturbance" for e in events):
            self.last_disturbance_hit = t
        if self.alarm and t - self.last_disturbance_hit >= c.alarm_clear_s:
            self.alarm = False

        if events:
            self.last_event, self.silent = t, False
        elif not self.silent and t - self.last_event >= c.silence_s:
            self.silent = True
            alerts.append({"type": "silence", "label": ""})

        self.indicators = [x for x in self.indicators if t - x[0] < c.score_window_s]
        self.disturbances = [x for x in self.disturbances if t - x[0] < c.score_window_s]
        bonus = min(c.bonus_cap, c.bonus_per_weight * sum(self.weights.get(l, 0) for l in self.species_heard()))
        penalty = min(c.penalty_cap, c.penalty_per_event * len(self.disturbances))
        self.score = max(0, min(100, c.base_score + bonus - penalty))
        return alerts

    def species_heard(self) -> list[str]:
        return sorted({label for _, label in self.indicators})
