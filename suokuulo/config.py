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
    weight: int = 0


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
    hits_needed: int = 2
    hit_window: int = 3
    confirm_single: float | None = None  # one window at or above this also confirms
    species_single: dict | None = None   # per-label overrides of confirm_single
    cooldown_s: float = 30
    # score and alerts
    base_score: int = 50
    score_window_s: float = 600
    bonus_per_weight: int = 10
    bonus_cap: int = 50
    penalty_per_event: int = 15
    penalty_cap: int = 50
    alarm_clear_s: float = 20
    silence_s: float = 1800
    # outputs
    headline_species: str = "golden_plover"  # gets the double chirp
    mute: bool = False                        # buzzer off, matrix still works
    log_file: str = "events.csv"
    verbose: bool = False                     # print raw detections for every window
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    # demo playlist: [path, max_windows] pairs, played with realtime=True
    demo: list | None = None


def load(path) -> Config:
    """`include: other.yaml` loads that file first; keys in this file override it."""
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    if "include" in data:
        data = {**yaml.safe_load((path.parent / data.pop("include")).read_text()), **data}
    cfg = Config(**data)
    cfg.species_file = str(path.parent / cfg.species_file)
    return cfg


def load_species(path) -> list[Species]:
    return [Species(**s) for s in yaml.safe_load(Path(path).read_text())["species"]]
