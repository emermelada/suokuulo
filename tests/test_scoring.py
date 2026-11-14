from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from suokuulo import config
from suokuulo.classifier import Detection
from suokuulo.eventlog import EventLog
from suokuulo.scoring import Baseline, Soundscape, health, health_label

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Helsinki")
SPECIES = config.load_species(ROOT / "config/species.yaml")


def at(*args):
    """Epoch seconds of a Helsinki local time."""
    return datetime(*args, tzinfo=TZ).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def cfg(**kw):
    c = config.Config(baseline_file=str(ROOT / "config/baseline.yaml"), **kw)
    return c


def bird(label="golden_plover"):
    return Detection(label, "indicator", 0.9)


def noise(label):
    return Detection(label, "disturbance", 0.9)


def soundscape(clock, log_path=None, **kw):
    return Soundscape(cfg(**kw), SPECIES, clock, log_path)


def test_detection_minutes_count_a_species_once_per_minute():
    clock = Clock(at(2026, 6, 10, 10, 0, 0))
    s = soundscape(clock, baseline_profile="breeding")
    for second in (0, 10, 50):          # three confirmations in one minute
        clock.t = at(2026, 6, 10, 10, 0, second)
        s.update([bird()])
    clock.t = at(2026, 6, 10, 10, 1, 5)  # and one in the next minute
    s.update([bird()])
    assert s.health()["observed"]["golden_plover"] == 2
    row = next(r for r in s.snapshot()["species"] if r["id"] == "golden_plover")
    assert (row["detections_today"], row["minutes_today"]) == (4, 2)


def test_richness_and_activity_math():
    weights = {"golden_plover": 3, "curlew": 1}
    expected = {"golden_plover": 2.0, "curlew": 4.0, "whimbrel": 0}  # whimbrel not expected now
    h = health({"golden_plover": 1, "curlew": 0}, expected, weights)
    assert h["richness"] == pytest.approx(3 / 4)
    assert h["activity"] == pytest.approx((3 * 0.5 + 1 * 0) / 4)
    assert h["score"] == round(100 * (0.6 * 0.75 + 0.4 * 0.375))  # 60
    full = health({"golden_plover": 5, "curlew": 9, "whimbrel": 3}, expected, weights)
    assert full == {"score": 100, "richness": 1.0, "activity": 1.0}  # both capped at 1
    assert health({}, {"curlew": 0}, weights) is None  # nothing expected: no score
    assert [health_label(s) for s in (39, 40, 69, 70)] == ["Poor", "Fair", "Fair", "Good"]


def test_profile_by_date_and_override():
    b = Baseline(ROOT / "config/baseline.yaml")
    assert [b.profile(date(2026, m, 15)) for m in (1, 4, 6, 9, 11)] == \
        ["winter", "migration", "breeding", "migration", "winter"]
    assert Baseline(ROOT / "config/baseline.yaml", "breeding").profile(date(2026, 11, 14)) == "breeding"
    assert [b.period(h) for h in (2, 3, 7, 21, 22)] == ["night", "dawn", "day", "day", "night"]


def test_counters_reset_at_local_midnight():
    clock = Clock(at(2026, 6, 10, 23, 50))
    s = soundscape(clock, baseline_profile="breeding")
    s.update([bird()])
    clock.t = at(2026, 6, 11, 0, 10)  # 20 min later, a new day in Helsinki
    s.update([])
    plover = next(r for r in s.snapshot()["species"] if r["id"] == "golden_plover")
    assert plover["detections_today"] == 0
    assert sum(plover["hourly"]) == 1 and plover["last_ago_s"] == 1200  # still in the 24 h view


def test_counters_rebuilt_from_events_csv(tmp_path):
    log = EventLog(tmp_path / "events.csv")
    log.write("2026-06-10T05:00:10+03:00", "golden_plover", "indicator", "0.9", "70")
    log.write("2026-06-10T05:00:40+03:00", "golden_plover", "indicator", "0.8", "70")
    log.write("2026-06-10T02:02:00", "curlew", "indicator", "0.7", "75")  # old rows: no offset, UTC
    log.write("2026-06-10T05:03:00+03:00", "engine", "disturbance", "0.5", "75")
    log.write("2026-06-10T05:04:00+03:00", "", "silence", "", "75")
    log.write("2026-06-09T05:00:00+03:00", "curlew", "indicator", "0.7", "75")  # yesterday
    log.file.close()
    s = soundscape(Clock(at(2026, 6, 10, 6, 0)), tmp_path / "events.csv", baseline_profile="breeding")
    snap = s.snapshot()
    rows = {r["id"]: r for r in snap["species"]}
    assert (rows["golden_plover"]["detections_today"], rows["golden_plover"]["minutes_today"]) == (2, 1)
    assert rows["golden_plover"]["first_today"] == "2026-06-10T05:00:10+03:00"
    assert rows["curlew"]["detections_today"] == 1
    assert [e["label"] for e in snap["events"]] == ["curlew", "golden_plover", "golden_plover"]  # old engine row dropped


def test_silence_alert_once():
    clock = Clock(at(2026, 6, 10, 12, 0))
    s = soundscape(clock, baseline_profile="breeding")
    clock.t += 1799
    assert s.update([]) == []
    clock.t += 1
    assert s.update([noise("human_voice")]) == [{"type": "silence", "label": ""}]  # people are not birds
    clock.t += 100
    assert s.update([]) == []


def test_baseline_learned_after_three_days(tmp_path):
    log = EventLog(tmp_path / "events.csv")
    for day, minutes in ((7, 4), (8, 6), (9, 0)):  # plover minutes at 05:xx on three past days
        for m in range(minutes):
            log.write(f"2026-06-{day:02d}T05:{m:02d}:00+03:00", "golden_plover", "indicator", "0.9", "")
        log.write(f"2026-06-{day:02d}T12:00:00+03:00", "curlew", "indicator", "0.9", "")
    log.file.close()
    clock = Clock(at(2026, 6, 10, 5, 30))
    s = soundscape(clock, tmp_path / "events.csv", baseline_profile="breeding", score_window_min=60)
    s.update([])
    assert s.baseline.source() == "learned from 3 days"
    assert s.health()["expected"] == {"golden_plover": 4}  # median of 4, 6, 0; curlew only at noon


@pytest.mark.parametrize("month", [11, 12, 1, 2])
def test_winter_profile_by_date(month):
    assert Baseline(ROOT / "config/baseline.yaml").profile(date(2026, month, 10)) == "winter"


def test_winter_is_off_season():
    clock = Clock(at(2026, 1, 15, 9, 0))
    s = soundscape(clock)  # profile picked by month
    h = s.snapshot()["health"]
    assert (h["profile"], h["off_season"], h["score"]) == ("winter", True, None)
    assert h["label"] == "Off season (low bird activity expected)"
    clock.t = at(2026, 6, 15, 5, 0)  # breeding dawn: a number again
    assert soundscape(clock).health()["off_season"] is False


def test_acoustic_index_per_minute_never_changes_health():
    import numpy as np
    from suokuulo.audio import band_power, ndsi
    t = np.arange(144000) / 48000
    assert ndsi(*band_power(np.fft.rfft(np.sin(2 * np.pi * 1500 * t)), [(1000, 2000), (2000, 8000)])) < -0.99
    assert ndsi(*band_power(np.fft.rfft(np.sin(2 * np.pi * 4000 * t)), [(1000, 2000), (2000, 8000)])) > 0.99
    clock = Clock(at(2026, 6, 10, 5, 0, 0))
    s = soundscape(clock, baseline_profile="breeding", score_window_min=10)
    s.update([bird()])
    before = s.health()["score"]
    for anthro, bio in ((3.0, 1.0), (3.0, 1.0), (1.0, 0.0)):  # three windows in minute 05:00
        clock.t += 15
        s.update([], bands=(anthro, bio))
    clock.t = at(2026, 6, 10, 5, 1, 30)  # 05:00 is now complete
    s.update([], bands=(0.0, 1.0))
    index = s.snapshot()["acoustic_index"]
    assert index["minute"] == index["window"] == round((2 - 7) / 9, 2)  # summed bands, not mean of ratios
    assert s.health()["score"] == before


def test_disturbance_is_off_by_default_and_never_changes_anything():
    clock = Clock(at(2026, 6, 10, 5, 0))
    s = soundscape(clock, baseline_profile="breeding", score_window_min=10)
    s.update([bird()])
    before = s.snapshot()
    for label in ("human_voice", "engine", "power_tools", "gun", "human_voice"):
        clock.t += 60
        assert s.update([noise(label)], alert_hit=True) == []
    after = s.snapshot()
    assert after["health"]["score"] == before["health"]["score"] and not s.alarm
    assert "disturbance" not in after and [e["label"] for e in after["events"]] == ["golden_plover"]
    assert "disturbance" in soundscape(clock, disturbance_enabled=True).snapshot()  # the future-work path


def test_active_species_leaves_out_disturbance_unless_enabled():
    c = config.load(ROOT / "config/demo.yaml")
    assert {s.kind for s in config.active_species(c)} == {"indicator"}
    c.disturbance_enabled = True
    assert "human_voice" in {s.id for s in config.active_species(c)}
