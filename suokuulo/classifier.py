import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .audio import highpass_gain


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


class BirdNetClassifier:
    """BirdNET v2.4 TFLite model run directly with ai-edge-litert.

    Model and labels are the files shipped in the birdnetlib package, but
    birdnetlib itself is not imported: it would load librosa, matplotlib and a
    second (location) model, ~95 MB of RAM we never use. Same maths as
    birdnetlib's Analyzer: sigmoid(clip(logit, -15, 15)). No lat/lon/date
    filter, only our species list.

    BirdNET is multi-label (one sigmoid per label): every label in our list is
    scored on every window and returned if above min_conf, never just the top one.
    """

    def __init__(self, species, min_conf=0.1, highpass_hz=0):
        t0 = time.perf_counter()
        try:
            from ai_edge_litert.interpreter import Interpreter
        except ImportError:  # same API, older Pythons
            from tflite_runtime.interpreter import Interpreter
        models = Path(importlib.util.find_spec("birdnetlib").submodule_search_locations[0]) / "models/analyzer"
        labels = (models / "BirdNET_GLOBAL_6K_V2.4_Labels.txt").read_text().splitlines()
        missing = sorted({s.label for s in species} - set(labels))
        if missing:
            raise ValueError(f"labels not in model, fix species.yaml: {missing}")
        self.interpreter = Interpreter(model_path=str(models / "BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite"),
                                       num_threads=1)
        self.interpreter.allocate_tensors()
        self.input = self.interpreter.get_input_details()[0]["index"]    # [1, 144000]
        self.output = self.interpreter.get_output_details()[0]["index"]  # [1, 6522] logits
        self.species, self.min_conf = species, min_conf
        self.columns = np.array([labels.index(s.label) for s in species])
        self.highpass = highpass_gain(highpass_hz) if highpass_hz else None
        self.spectrum = None  # rfft of the last raw window, reused for the acoustic index
        self.load_s = time.perf_counter() - t0
        print(f"[birdnet] imports + model load {self.load_s:.2f} s")

    def classify(self, window, sample_rate):
        if sample_rate != 48000 or window.shape != (144000,):
            raise ValueError(f"BirdNET needs 3 s at 48 kHz, got {window.shape} at {sample_rate} Hz")
        self.spectrum = None
        if self.highpass is not None:
            self.spectrum = np.fft.rfft(window)
            window = np.fft.irfft(self.spectrum * self.highpass, len(window))
        self.interpreter.set_tensor(self.input, window.astype(np.float32, copy=False)[None])
        self.interpreter.invoke()
        logits = self.interpreter.get_tensor(self.output)[0, self.columns]
        conf = 1 / (1 + np.exp(-np.clip(logits, -15, 15)))
        return [Detection(s.id, s.kind, float(c)) for s, c in zip(self.species, conf) if c > self.min_conf]
