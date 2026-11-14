import io
import sys
import time
import types
from contextlib import redirect_stdout
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


def _alias_litert():
    """birdnetlib imports tflite_runtime, else tensorflow. tflite-runtime has no
    wheels past Python 3.11; ai-edge-litert is its official successor with the
    same Interpreter API and wheels for cp310-cp314 on x86_64 and aarch64."""
    try:
        import tflite_runtime.interpreter  # noqa: F401
        return
    except ImportError:
        pass
    try:
        import ai_edge_litert.interpreter as litert
    except ImportError:
        return  # birdnetlib falls back to tensorflow
    pkg = types.ModuleType("tflite_runtime")
    pkg.interpreter = litert
    sys.modules["tflite_runtime"] = pkg
    sys.modules["tflite_runtime.interpreter"] = litert


class BirdNetClassifier:
    """BirdNET v2.4 via birdnetlib. No lat/lon/date: species list filter only."""

    def __init__(self, species, min_conf=0.1):
        t0 = time.perf_counter()  # includes imports: librosa + runtime are most of the startup cost
        _alias_litert()
        from birdnetlib import RecordingBuffer
        from birdnetlib.analyzer import Analyzer
        self.RecordingBuffer, self.min_conf = RecordingBuffer, min_conf
        self.by_label = {s.label: s for s in species}
        with redirect_stdout(io.StringIO()):  # birdnetlib prints on every call
            self.analyzer = Analyzer(custom_species_list=list(self.by_label))
        self.load_s = time.perf_counter() - t0
        missing = set(self.by_label) - set(self.analyzer.labels)
        if missing:
            raise ValueError(f"labels not in model, fix species.yaml: {sorted(missing)}")
        print(f"[birdnet] imports + model load {self.load_s:.2f} s")

    def classify(self, window, sample_rate):
        rec = self.RecordingBuffer(self.analyzer, window, sample_rate, min_conf=self.min_conf)
        with redirect_stdout(io.StringIO()):
            rec.analyze()
        return [Detection(s.id, s.kind, d["confidence"])
                for d in rec.detections if (s := self.by_label.get(d["label"]))]
