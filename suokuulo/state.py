"""Thread-safe snapshot of pipeline state for the dashboard."""
import threading
import time
from collections import deque


class State:
    def __init__(self, max_items=50):
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.score = None
        self.alarm = False
        self.recent = deque(maxlen=max_items)
        self.alerts = deque(maxlen=max_items)
        self.species = []
        self.inference_ms = None

    def update(self, iso_time, events, alerts, score, alarm, species_heard, inference_ms):
        with self.lock:
            for e in events:
                self.recent.append({"time": iso_time, "label": e.label, "kind": e.kind,
                                    "confidence": round(e.confidence, 2)})
            for a in alerts:
                self.alerts.append({"time": iso_time, **a})
            self.score, self.alarm, self.species = score, alarm, species_heard
            self.inference_ms = round(inference_ms)

    def snapshot(self) -> dict:
        with self.lock:
            return {"score": self.score, "alarm": self.alarm,
                    "recent": list(reversed(self.recent)), "alerts": list(reversed(self.alerts)),
                    "species_heard_10min": list(self.species),
                    "uptime_s": round(time.monotonic() - self.started),
                    "inference_ms": self.inference_ms}
