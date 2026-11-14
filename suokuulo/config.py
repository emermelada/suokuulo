"""Flat dataclass config loaded from YAML. Unknown keys fail loudly."""
from dataclasses import dataclass
from pathlib import Path

import yaml


VOICE = "human_voice"  # species.yaml id of BirdNET's "Human vocal" label


@dataclass
class Species:
    id: str        # our internal id, e.g. "golden_plover"
    label: str     # exact BirdNET label, "Scientific name_Common Name"
    kind: str      # "indicator" | "disturbance"
    group: str = ""  # disturbances: people | machinery | gunshot | other


@dataclass
class Config:
    # audio
    source: str = "file"          # file | mic | arecord | applab
    input: str = "test_clips"     # file or folder for source=file
    loop: bool = False
    realtime: bool = False
    device: str | int | None = None
    # classifier
    classifier: str = "birdnet"   # birdnet | mock
    min_conf: float = 0.1         # BirdNET's own floor; our thresholds are below
    highpass_hz: float = 1000     # high-pass before inference (speech, wind, hum); 0 = off
    species_file: str = "species.yaml"  # relative to the config file
    # detection (section 7)
    hop_s: float = 3.0                # a 3 s window every hop_s seconds; < 3 overlaps them
    indicator_hit: float = 0.50
    disturbance_hit: float = 0.35
    species_hit: dict | None = None   # per-label overrides, e.g. {golden_plover: 0.35}
    any_disturbance_hit: float | None = None  # pool every disturbance but human voice into one
                                              # signal (max per window); None = each label alone
    hits_needed: int = 2
    hit_window: int = 3
    confirm_single: float | None = None  # one window at or above this also confirms
    species_single: dict | None = None   # per-label overrides of confirm_single
    cooldown_s: float = 30
    # soundscape health: indicator birds only, against config/baseline.yaml
    baseline_file: str = "baseline.yaml"  # relative to the config file
    baseline_profile: str | None = None   # breeding | migration | winter; null = by month
    score_window_min: float = 60          # rolling window for detection-minutes
    richness_weight: float = 0.6
    activity_weight: float = 0.4
    learn_min_days: int = 3               # days of events.csv before the baseline is learned
    off_season_below: float = 3           # expected detection-minutes per hour (all species) under
                                          # which health shows "Off season" instead of a number
    timezone: str = "Europe/Helsinki"     # days, hours and midnight reset
    # disturbance pressure: reported apart, never lowers health
    pressure_minutes: tuple = (5, 15)     # disturbed minutes in the last hour: Moderate, High
    alarm_clear_s: float = 20             # machinery alert clears this long after its last hit
    silence_s: float = 1800               # alert after this long without a bird
    # outputs
    site_name: str = ""
    headline_species: str = "golden_plover"  # gets the double chirp
    buzzer_startup: bool = True               # one beep when the app starts
    buzzer_alerts: bool = False               # bird chirps + machinery siren; LED matrix always works
    log_file: str = "events.csv"
    verbose: bool = False                     # print raw detections for every window
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    # demo playlist: [path, max_windows] pairs, played with realtime=True
    demo: list | None = None


def read(path) -> dict:
    """YAML dict; `include: other.yaml` loads that file first and this file overrides it."""
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    if "include" in data:
        data = {**read(path.parent / data.pop("include")), **data}
    return data


def load(path) -> Config:
    path = Path(path)
    cfg = Config(**read(path))
    cfg.species_file = str(path.parent / cfg.species_file)
    cfg.baseline_file = str(path.parent / cfg.baseline_file)
    return cfg


def load_species(path) -> list[Species]:
    return [Species(**s) for s in yaml.safe_load(Path(path).read_text())["species"]]
