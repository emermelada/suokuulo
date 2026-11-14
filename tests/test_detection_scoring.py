from suokuulo.classifier import Detection
from suokuulo.config import Config
from suokuulo.detection import Smoother
from suokuulo.scoring import ScoreEngine

WEIGHTS = {"golden_plover": 3, "common_snipe": 1, "curlew": 1, "whimbrel": 1,
           "meadow_pipit": 1, "common_crane": 1}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def bird(label="golden_plover", c=0.8):
    return Detection(label, "indicator", c)


def noise(label="engine", c=0.6):
    return Detection(label, "disturbance", c)


def feed(smoother, clock, windows, step=3.0):
    """Run windows through the smoother, return list of event label lists per window."""
    out = []
    for dets in windows:
        out.append([e.label for e in smoother.update(dets)])
        clock.t += step
    return out


def test_two_of_three_confirms():
    clock = Clock()
    s = Smoother(Config(), clock)
    assert feed(s, clock, [[bird()], [], [bird()]]) == [[], [], ["golden_plover"]]


def test_two_hits_spread_over_four_windows_do_not_confirm():
    clock = Clock()
    s = Smoother(Config(), clock)
    assert feed(s, clock, [[bird()], [], [], [bird()]]) == [[], [], [], []]


def test_thresholds_per_kind():
    clock = Clock()
    s = Smoother(Config(), clock)
    # 0.45 is below the indicator threshold (0.50) but above disturbance (0.35)
    assert feed(s, clock, [[bird(c=0.45)], [bird(c=0.45)]]) == [[], []]
    assert feed(s, clock, [[noise(c=0.36)], [noise(c=0.36)]]) == [[], ["engine"]]


def test_cooldown():
    clock = Clock()
    s = Smoother(Config(), clock)
    events = feed(s, clock, [[bird()]] * 12)  # 36 s of continuous song
    confirmed_at = [i for i, e in enumerate(events) if e]
    assert confirmed_at == [1, 11]  # t=3, then t=33 (>= 30 s later)


def score_after(events, clock=None, **cfg):
    clock = clock or Clock()
    eng = ScoreEngine(Config(**cfg), WEIGHTS, clock)
    eng.update(events)
    return eng


def test_distinct_species_counted_once():
    clock = Clock()
    eng = ScoreEngine(Config(), WEIGHTS, clock)
    eng.update([bird("common_snipe")])
    clock.t += 60
    eng.update([bird("common_snipe")])
    assert eng.score == 60  # 50 + 10 * 1, not 50 + 10 * 2


def test_weights_and_bonus_cap():
    assert score_after([bird("golden_plover")]).score == 80
    many = [bird(l) for l in WEIGHTS]  # weights sum to 8 -> 80, capped at 50
    assert score_after(many).score == 100


def test_penalty_cap_and_clamp():
    assert score_after([noise()]).score == 35
    assert score_after([noise()] * 5).score == 0       # 75 capped at 50 -> 50 - 50
    assert score_after([noise()] * 5, base_score=20).score == 0  # clamp at 0
    assert score_after([bird(l) for l in WEIGHTS], base_score=80).score == 100  # clamp at 100


def test_alarm_raise_and_clear():
    clock = Clock()
    eng = ScoreEngine(Config(), WEIGHTS, clock)
    alerts = eng.update([noise()])
    assert eng.alarm and alerts == [{"type": "disturbance", "label": "engine"}]
    clock.t = 15
    eng.update([], disturbance_hit=True)  # a further hit pushes the clear time out
    clock.t = 34
    eng.update([])
    assert eng.alarm
    clock.t = 35
    eng.update([])
    assert not eng.alarm


def test_events_expire_after_600s():
    clock = Clock()
    eng = ScoreEngine(Config(), WEIGHTS, clock)
    eng.update([bird("golden_plover"), noise()])
    assert eng.score == 65
    clock.t = 599
    eng.update([])
    assert eng.score == 65
    clock.t = 600
    eng.update([])
    assert eng.score == 50 and eng.species_heard() == []


def test_silence_alert_once():
    clock = Clock()
    eng = ScoreEngine(Config(), WEIGHTS, clock)
    clock.t = 1799
    assert eng.update([]) == []
    clock.t = 1800
    assert eng.update([]) == [{"type": "silence", "label": ""}]
    clock.t = 1900
    assert eng.update([]) == []
