"""Soundscape health from indicator birds. Disturbance pressure (people,
machinery, gunshots) is an optional code path behind disturbance_enabled
(default off, future work): when off, disturbance events are dropped here and
never reach the dashboard, the log or the MCU.

Health (0-100) uses indicator birds only, compared with what a healthy site is
expected to sound like (config/baseline.yaml), over the last score_window_min:
    richness = weight of species heard / weight of species expected (max 1)
    activity = weighted mean over expected species of
               min(1, detection-minutes heard / detection-minutes expected)
    health   = round(100 * (0.6 * richness + 0.4 * activity))
A detection-minute counts once per species, so one loud bird cannot inflate it.
Disturbance (people, machinery, gunshots) is counted on its own and never
lowers health.

Time is epoch seconds from an injectable clock. Days, hours and midnight are
local time in cfg.timezone. All counters are derived from the event list, so
they reset at local midnight by themselves and a restart rebuilds them from
events.csv.
"""
import csv
import statistics
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .audio import ndsi

ALERT_GROUPS = {"machinery", "gunshot"}  # the only disturbances that raise the alarm
GROUP_NAMES = {"people": "People nearby", "machinery": "Machinery", "gunshot": "Gunshot", "other": "Other"}
KEEP_S = 25 * 3600  # events kept in memory: 24 h sparkline + today


def health(observed, expected, weights, richness_weight=0.6, activity_weight=0.4):
    """observed / expected: species -> detection-minutes in the window.
    Returns {score, richness, activity}, or None when nothing is expected."""
    expected = {s: e for s, e in expected.items() if e > 0}
    if not expected:
        return None
    total = sum(weights.get(s, 1) for s in expected)
    richness = min(1.0, sum(weights.get(s, 1) for s, n in observed.items() if n) / total)
    activity = sum(weights.get(s, 1) * min(1.0, observed.get(s, 0) / e) for s, e in expected.items()) / total
    return {"score": round(100 * (richness_weight * richness + activity_weight * activity)),
            "richness": richness, "activity": activity}


OFF_SEASON = "Off season (low bird activity expected)"


def health_label(score):
    return OFF_SEASON if score is None else "Poor" if score < 40 else "Fair" if score < 70 else "Good"


class Baseline:
    """Expected detection-minutes per hour, by season profile and part of day,
    or learned per hour of day from past days of events.csv."""

    def __init__(self, path, profile=None):
        data = yaml.safe_load(Path(path).read_text())
        self.periods, self.profiles, self.override = data["periods"], data["profiles"], profile
        self.learned, self.learned_days = {}, 0

    def profile(self, day: date) -> str:
        return self.override or next(n for n, p in self.profiles.items() if day.month in p["months"])

    def period(self, hour) -> str:
        p = self.periods
        return "dawn" if p["dawn"] <= hour < p["day"] else "day" if p["day"] <= hour < p["night"] else "night"

    def expected(self, local: datetime):
        """(species -> expected detection-minutes per hour, species -> weight)."""
        species = self.profiles[self.profile(local.date())]["species"] or {}
        weights = {s: v.get("weight", 1) for s, v in species.items()}
        if self.learned:
            return {s: hours[local.hour] for s, hours in self.learned.items()}, weights
        return {s: v.get(self.period(local.hour), 0) for s, v in species.items()}, weights

    def learn(self, events, today: date, tz, min_days):
        """Median detection-minutes per hour of day over past days, once there
        are at least min_days of them. events: (t, label, kind, confidence)."""
        minutes, days = {}, set()
        for t, label, kind, _ in events:
            local = datetime.fromtimestamp(t, tz)
            if kind == "indicator" and local.date() < today:
                days.add(local.date())
                minutes.setdefault((local.date(), local.hour, label), set()).add(local.minute)
        self.learned_days = len(days)
        labels = {label for _, _, label in minutes}
        self.learned = {} if len(days) < min_days else {
            label: [statistics.median(len(minutes.get((d, h, label), ())) for d in days) for h in range(24)]
            for label in labels}

    def source(self) -> str:
        return f"learned from {self.learned_days} days" if self.learned else "configured"


def read_log(path):
    """(t, label, kind, confidence) of every event in events.csv; bad rows skipped.
    Rows without a UTC offset come from before the offset was logged, written
    by the App Lab container, whose clock is UTC."""
    if not path or not Path(path).exists():
        return []
    out = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                dt = datetime.fromisoformat(row["iso_time"])
                if row["label"]:
                    out.append(((dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp(),
                                row["label"], row["kind"], float(row["confidence"] or 0)))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def minutes(events):
    return len({int(e[0] // 60) for e in events})


class Soundscape:
    def __init__(self, cfg, species, now=time.time, log_path=None):
        self.cfg, self.now, self.log_path = cfg, now, log_path
        self.tz = ZoneInfo(cfg.timezone)
        self.species = species
        self.group = {s.id: s.group for s in species}
        self.baseline = Baseline(cfg.baseline_file, cfg.baseline_profile)
        t = now()
        self.events = [e for e in read_log(log_path) if e[0] > t - KEEP_S and self.kept(e[2])]  # after a restart
        self.bands = {}  # minute -> [anthrophony, biophony] power summed over its windows (not logged)
        self.day = None
        self.alarm, self.silent = False, False
        self.last_alert_hit, self.last_bird = None, t

    def kept(self, kind):
        return kind == "indicator" or self.cfg.disturbance_enabled

    def local(self, t=None):
        return datetime.fromtimestamp(self.now() if t is None else t, self.tz)

    def update(self, events, alert_hit=False, bands=None) -> list[dict]:
        """Record one window's confirmed events; return new alerts as {type, label}.
        alert_hit: a machinery/gunshot label hit this window (keeps the alarm on).
        bands: the window's (anthrophony, biophony) power for the acoustic index."""
        t, c = self.now(), self.cfg
        if bands is not None:
            total = self.bands.setdefault(int(t // 60), [0.0, 0.0])
            total[0] += bands[0]
            total[1] += bands[1]
        if self.local(t).date() != self.day:  # midnight (or startup): relearn the baseline
            self.day = self.local(t).date()
            self.baseline.learn(read_log(self.log_path), self.day, self.tz, c.learn_min_days)
        alerts = []
        events = [e for e in events if self.kept(e.kind)]
        for e in events:
            self.events.append((t, e.label, e.kind, e.confidence))
            if self.group.get(e.label) in ALERT_GROUPS:
                alerts.append({"type": "disturbance", "label": e.label})
                self.alarm = True
        if alert_hit or alerts:
            self.last_alert_hit = t
        if self.alarm and t - self.last_alert_hit >= c.alarm_clear_s:
            self.alarm = False
        if any(e.kind == "indicator" for e in events):
            self.last_bird, self.silent = t, False
        elif not self.silent and t - self.last_bird >= c.silence_s:
            self.silent = True
            alerts.append({"type": "silence", "label": ""})
        self.events = [e for e in self.events if e[0] > t - KEEP_S]
        self.bands = {m: v for m, v in self.bands.items() if m * 60 > t - KEEP_S}
        return alerts

    def acoustic_index(self) -> dict:
        """NDSI per minute: latest complete minute, mean over the health window, 24 hourly means."""
        t = self.now()
        per_minute = {m: ndsi(a, b) for m, (a, b) in self.bands.items() if m < int(t // 60)}
        first_hour = (int(t) // 3600 - 23) * 3600
        hourly = [[] for _ in range(24)]
        for m, v in per_minute.items():
            if m * 60 >= first_hour:
                hourly[(m * 60 - first_hour) // 3600].append(v)
        recent = [v for m, v in per_minute.items() if m * 60 >= t - self.cfg.score_window_min * 60]

        def mean(xs):
            return round(statistics.mean(xs), 2) if xs else None

        return {"minute": round(per_minute[max(per_minute)], 2) if per_minute else None,
                "window": mean(recent), "hourly": [mean(h) for h in hourly]}

    def health(self) -> dict:
        t, c = self.now(), self.cfg
        local = self.local(t)
        per_hour, weights = self.baseline.expected(local)
        scale = c.score_window_min / 60
        since = t - c.score_window_min * 60
        observed = {s.id: minutes([e for e in self.events if e[1] == s.id and e[0] >= since])
                    for s in self.species if s.kind == "indicator"}
        expected = {s: n * scale for s, n in per_hour.items()}
        off_season = sum(per_hour.values()) < c.off_season_below  # e.g. winter: a number would mislead
        h = (not off_season and health(observed, expected, weights, c.richness_weight, c.activity_weight)) or \
            {"score": None, "richness": None, "activity": None}
        return {**h, "label": health_label(h["score"]), "off_season": h["score"] is None,
                "profile": self.baseline.profile(local.date()),
                "baseline": self.baseline.source(), "window_min": c.score_window_min,
                "observed": observed, "expected": {s: round(e, 2) for s, e in expected.items() if e > 0}}

    def snapshot(self) -> dict:
        """Everything the dashboard shows apart from uptime, timing and RAM."""
        t = self.now()
        local = self.local(t)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        first_hour = (int(t) // 3600 - 23) * 3600  # 24 one-hour bars, the last is the current hour
        today = [e for e in self.events if e[0] >= midnight]
        h = self.health()

        def iso(e):
            return self.local(e[0]).isoformat(timespec="seconds") if e else None

        rows = []
        for s in self.species:
            if s.kind != "indicator":
                continue
            mine = [e for e in self.events if e[1] == s.id]
            mine_today = [e for e in today if e[1] == s.id]
            hourly = [0] * 24
            for m in {int(e[0] // 60) for e in mine if e[0] >= first_hour}:
                hourly[(m * 60 - first_hour) // 3600] += 1
            latin, common = s.label.split("_", 1)
            rows.append({"id": s.id, "common": common, "latin": latin,
                         "expected": s.id in h["expected"], "heard_in_window": h["observed"][s.id] > 0,
                         "detections_today": len(mine_today), "minutes_today": minutes(mine_today),
                         "first_today": iso(mine_today[0] if mine_today else None),
                         "last": iso(mine[-1] if mine else None),
                         "last_ago_s": round(t - mine[-1][0]) if mine else None, "hourly": hourly})

        names = {s.id: s.label.split("_", 1)[1] for s in self.species}

        def entry(e):
            return {"time": iso(e), "label": e[1], "name": names.get(e[1], e[1]), "kind": e[2],
                    "group": self.group.get(e[1], ""), "confidence": round(e[3], 2)}

        birds_today = [e for e in today if e[2] == "indicator"]
        heard = {r["id"] for r in rows if r["detections_today"]}
        summary = {"species_heard": len(heard), "expected": len(h["expected"]),
                   "expected_heard": len(heard & set(h["expected"])), "detections": len(birds_today),
                   "first": iso(birds_today[0] if birds_today else None),
                   "last": iso(birds_today[-1] if birds_today else None),
                   "hourly": [sum(r["hourly"][i] for r in rows) for i in range(24)]}
        snap = {"health": {k: v for k, v in h.items() if k not in ("observed", "expected")},
                "today": summary, "species": rows, "acoustic_index": self.acoustic_index(),
                "events": [entry(e) for e in self.events[-20:][::-1]]}
        if self.cfg.disturbance_enabled:
            snap["disturbance"] = self.disturbance(t, midnight, iso, entry)
        return snap

    def disturbance(self, t, midnight, iso, entry) -> dict:
        """Future work, off by default: per-group counts and a pressure level."""
        groups = []
        for g in GROUP_NAMES:
            mine = [e for e in self.events if self.group.get(e[1]) == g]
            if g in self.group.values():
                mine_today = [e for e in mine if e[0] >= midnight]
                groups.append({"group": g, "name": GROUP_NAMES[g], "alert": g in ALERT_GROUPS,
                               "events_today": len(mine_today), "minutes_today": minutes(mine_today),
                               "last": iso(mine[-1] if mine else None)})
        pressing = [e for e in self.events if e[0] > t - 3600 and e[2] == "disturbance" and self.group.get(e[1]) != "people"]
        moderate, high = self.cfg.pressure_minutes
        hour_minutes = minutes(pressing)
        disturbances = [e for e in self.events if e[2] == "disturbance"]
        level = "High" if hour_minutes >= high else "Moderate" if hour_minutes >= moderate else "Low"
        return {"alarm": self.alarm, "groups": groups, "hour_minutes": hour_minutes,
                "level": level, "last": entry(disturbances[-1]) if disturbances else None}
