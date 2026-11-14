"""Overlaid clips through the real model with the board's detection settings:
a bird must still be confirmed when people talk over it, and two species
calling at once must both be confirmed (BirdNET is multi-label; nothing keeps
only the top label). Needs fetched clips; skipped otherwise."""
from pathlib import Path

import numpy as np
import pytest

from suokuulo import config
from suokuulo.audio import load_audio, split_windows
from suokuulo.classifier import BirdNetClassifier
from suokuulo.detection import Smoother
from suokuulo.pipeline import simulated

ROOT = Path(__file__).resolve().parents[1]
CLIPS = {"plover": "golden_plover/XC1193791.wav", "speech": "human_voice/LIBRISPEECH-1673-143396-0013.flac",
         "crane": "common_crane/XC1174838.wav", "curlew": "curlew/XC1140522.mp3"}
pytestmark = pytest.mark.skipif(not all((ROOT / "test_clips" / c).exists() for c in CLIPS.values()),
                                reason="run scripts/fetch_bird_clips.py and fetch_noise_clips.py --speech 10")


@pytest.fixture(scope="module")
def model():
    cfg = config.load(ROOT / "config/laptop.yaml")
    species = config.load_species(cfg.species_file)
    return cfg, BirdNetClassifier(species, cfg.min_conf, cfg.highpass_hz)


def clip(name):
    return load_audio(ROOT / "test_clips" / CLIPS[name])


def equal_rms(a, b):
    """Overlay b on a at the same RMS level, b looped or cut to a's length."""
    b = np.tile(b, -(-len(a) // len(b)))[:len(a)]
    return a / np.sqrt(np.mean(a ** 2)) * 0.05 + b / np.sqrt(np.mean(b ** 2)) * 0.05


def confirmed(y, model):
    cfg, classifier = model
    windows, now = simulated(split_windows(y, int(cfg.hop_s * 48000)), cfg.hop_s)
    smoother = Smoother(cfg, now)
    return {e.label for w in windows for e in smoother.update(classifier.classify(w, 48000))}


def test_bird_confirmed_while_people_talk(model):
    assert "golden_plover" in confirmed(equal_rms(clip("plover"), clip("speech")), model)


def test_two_species_at_once(model):
    crane, curlew = clip("crane"), clip("curlew")
    n = min(len(crane), len(curlew))
    assert {"common_crane", "curlew"} <= confirmed(equal_rms(crane[:n], curlew[:n]), model)
