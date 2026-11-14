"""Main loop: audio window -> classifier -> smoother -> health and disturbance
-> display/log/state."""
import time

from .detection import Smoother
from .scoring import ALERT_GROUPS, Soundscape
from .state import memory

SAMPLE_RATE = 48000
STARTUP_BEEP = 2  # chirp kind 2: one beep when the app starts


class Pipeline:
    def __init__(self, cfg, species, classifier, display, now=time.time, state=None, log=None, verbose=False):
        self.cfg, self.classifier, self.display, self.now = cfg, classifier, display, now
        self.state, self.log, self.verbose = state, log, verbose
        self.smoother = Smoother(cfg, now)
        self.soundscape = Soundscape(cfg, species, now, log.path if log else None)
        self.windows, self.inference_ms, self.stats_at = 0, [], now()
        self.score, self.started = None, False

    def step(self, window, sample_rate=SAMPLE_RATE):
        t0 = time.perf_counter()
        detections = self.classifier.classify(window, sample_rate)
        inference_ms = (time.perf_counter() - t0) * 1000
        self.windows += 1
        self.inference_ms = (self.inference_ms + [inference_ms])[-20:]
        mean_ms = sum(self.inference_ms) / len(self.inference_ms)
        if self.verbose:
            raw = ", ".join(f"{d.label} {d.confidence:.2f}" for d in sorted(detections, key=lambda d: -d.confidence))
            print(f"  window {self.windows:4d} {inference_ms:5.0f} ms  {raw or '-'}")

        events = self.smoother.update(detections)
        group = self.soundscape.group
        alert_hit = any(group.get(d.label) in ALERT_GROUPS for d in self.smoother.hits)
        prev_alarm = self.soundscape.alarm
        alerts = self.soundscape.update(events, alert_hit)
        score = self.soundscape.health()["score"]
        t = self.now()
        iso = self.soundscape.local(t).isoformat(timespec="seconds")

        for e in events:
            print(f"{iso} window {self.windows:4d} EVENT {e.label} ({e.kind}) conf {e.confidence:.2f} health {score}")
            if e.kind == "indicator":
                self.display.chirp(int(e.label == self.cfg.headline_species))
        for a in alerts:
            print(f"{iso} window {self.windows:4d} ALERT {a['type']} {a['label']}")
        self.show_score(score)
        if self.soundscape.alarm != prev_alarm:  # machinery and gunshots only, never people
            self.display.alarm(self.soundscape.alarm)

        if self.log:  # labels and times only: audio is never stored
            for e in events:
                self.log.write(iso, e.label, e.kind, f"{e.confidence:.3f}", "" if score is None else score,
                               "disturbance" if group.get(e.label) in ALERT_GROUPS else "")
            for a in alerts:
                if a["type"] == "silence":
                    self.log.write(iso, "", "", "", "" if score is None else score, "silence")
        if t - self.stats_at >= 60:
            self.stats_at = t
            ram = memory()
            ram = f"board {ram['used_mb']}/{ram['total_mb']} MB used, app {ram['app_mb']} MB" if ram else "n/a"
            print(f"[stats] inference {mean_ms:.0f} ms/window (mean of last {len(self.inference_ms)}), RAM {ram}")
        if self.state:
            self.state.update(self.soundscape.snapshot(), mean_ms)
        return events

    def show_score(self, score):
        if score != self.score or not self.started:
            self.score = score
            self.display.show_score(-1 if score is None else score)

    def run(self, windows):
        if not self.started:  # App.run may call run() again if the mic stream ends
            if self.cfg.buzzer_startup:
                self.display.chirp(STARTUP_BEEP)
            self.display.mute(not self.cfg.buzzer_alerts)
            self.show_score(self.soundscape.health()["score"])
            self.started = True
            if self.state:
                self.state.update(self.soundscape.snapshot())
        for w in windows:
            self.step(w)


def simulated(windows, step_s=3.0, start=0.0):
    """Wrap a window iterator with a fake clock that advances step_s (the hop) per window.

    Returns (windows, now). Lets replays and evaluation run at full speed while
    cooldowns, minutes and expiry still see audio time. start: epoch seconds.
    """
    clock = [start]

    def gen():
        for w in windows:
            yield w
            clock[0] += step_s

    return gen(), lambda: clock[0]
