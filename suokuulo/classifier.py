from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Detection:
    label: str          # our internal id, e.g. "golden_plover", "engine"
    kind: str           # "indicator" | "disturbance"
    confidence: float   # 0..1


class Classifier(Protocol):
    def classify(self, window: np.ndarray, sample_rate: int) -> list[Detection]: ...


class MockClassifier:
    """Replays a script: one list of (label, confidence) per window, ignores audio."""

    def __init__(self, script, species):
        self.kind = {s.id: s.kind for s in species}
        self.script = iter(script)

    def classify(self, window, sample_rate):
        return [Detection(l, self.kind[l], c) for l, c in next(self.script, [])]
