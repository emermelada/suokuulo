"""Smoke test for applab/python/main.py with fake arduino.* modules: checks the
board wiring (mic re-chunking, Bridge calls, WebUI endpoint) on the laptop
with config/demo.yaml (breeding baseline, 10 min window).
Needs a fetched golden plover clip; skipped otherwise."""
import runpy
import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "test_clips/golden_plover/XC1193791.wav"


def fake_arduino(calls, api, rate):
    import soxr
    from suokuulo.audio import load_audio
    audio = soxr.resample(load_audio(CLIP), 48000, rate)

    class Microphone:
        USB_MIC_1 = "usb:1"

        def __init__(self, device, sample_rate, channels, format):
            self.name, self.sample_rate = device, rate  # a real mic may ignore the request

        def start(self):
            pass

        def stream(self):  # 1024-frame float32 chunks, like BUFFER_SIZE_BALANCED
            for i in range(0, len(audio), 1024):
                yield audio[i:i + 1024].astype(np.float32)

    class WebUI:
        def __init__(self, port):
            pass

        def expose_api(self, method, path, fn):
            api[method, path] = fn

    class Bridge:
        @staticmethod
        def call(name, *args, timeout=10):
            calls.append((name, *args))

        @staticmethod
        def notify(name, *args):
            calls.append((name, *args))

    class App:
        @staticmethod
        def run(user_loop):
            user_loop()  # the real App loops forever; once is enough here

    mods = {"arduino": types.ModuleType("arduino"),
            "arduino.app_utils": types.SimpleNamespace(App=App, Bridge=Bridge),
            "arduino.app_bricks": types.ModuleType("arduino.app_bricks"),
            "arduino.app_bricks.web_ui": types.SimpleNamespace(WebUI=WebUI),
            "arduino.app_peripherals": types.ModuleType("arduino.app_peripherals"),
            "arduino.app_peripherals.microphone": types.SimpleNamespace(Microphone=Microphone)}
    return mods


@pytest.mark.skipif(not CLIP.exists(), reason="run scripts/fetch_bird_clips.py first")
@pytest.mark.parametrize("rate", [48000, 44100])
def test_board_entrypoint_wiring(monkeypatch, rate):
    calls, api = [], {}
    for name, mod in fake_arduino(calls, api, rate).items():
        monkeypatch.setitem(sys.modules, name, mod)
    log = ROOT / "applab/events.csv"
    try:
        runpy.run_path(str(ROOT / "applab/python/main.py"), run_name="__main__")
    finally:
        log.unlink(missing_ok=True)
    assert calls[0] == ("beep", 1)  # startup beep, the buzzer's only sound
    assert {c[0] for c in calls} <= {"beep", "show_score", "summary", "heartbeat"}
    summary = next(c for c in calls if c[0] == "summary")  # sent once at start: nothing heard yet
    assert summary == ("summary", 0, 0, 0, 0, 0)
    scores = [c[1] for c in calls if c[0] == "show_score"]
    assert scores[0] == 0 and scores[-1] > 0  # nothing heard yet, then the plover raises health
    state = api["GET", "/api/state"]()
    assert state["health"]["score"] == scores[-1] and state["status"] == "listening"
    plover = next(r for r in state["species"] if r["id"] == "golden_plover")
    assert plover["detections_today"] >= 1 and state["events"][0]["label"] == "golden_plover"
