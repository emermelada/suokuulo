"""UNO Q App Lab entrypoint. The only Python in the project that imports arduino.*.

suokuulo/ and config/ sit next to this file (symlinks in the repo; copy with
`rsync -aL` so they become real folders on the board, see README.md).
"""
import sys
from pathlib import Path

import numpy as np
from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.microphone import Microphone
from arduino.app_utils import App, Bridge

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from suokuulo import config  # noqa: E402
from suokuulo.audio import SAMPLE_RATE, WINDOW, make_source  # noqa: E402
from suokuulo.classifier import BirdNetClassifier  # noqa: E402
from suokuulo.eventlog import EventLog  # noqa: E402
from suokuulo.pipeline import Pipeline  # noqa: E402
from suokuulo.state import State  # noqa: E402


class BridgeDisplay:
    """Display over the RouterBridge to sketch/sketch.ino. A failed call is logged, never fatal."""

    def _call(self, name, *args):
        try:
            Bridge.call(name, *args, timeout=2)
        except Exception as e:  # MCU not flashed or busy: keep listening anyway
            print(f"[bridge] {name}{args} failed: {e}")

    def show_score(self, score):
        self._call("show_score", int(score))

    def show_bird(self, species_index):
        self._call("show_bird", int(species_index))

    def alarm(self, on):
        self._call("alarm", bool(on))

    def chirp(self, kind):
        self._call("chirp", int(kind))

    def mute(self, on):
        self._call("mute", bool(on))


class AppLabMicSource:
    """USB mic through App Lab's Microphone peripheral (arecord/PortAudio may not
    be visible in the app container). Re-chunks its stream into 3 s windows."""
    sample_rate = SAMPLE_RATE

    def __init__(self, device=None):
        self.device = Microphone.USB_MIC_1 if device is None else device

    def windows(self):
        mic = Microphone(device=self.device, sample_rate=SAMPLE_RATE, channels=1, format="float32")
        mic.start()
        rate = mic.sample_rate  # TODO(hardware): confirm the USB mic really opens at 48 kHz
        print(f"[mic] {mic.name} at {rate} Hz")
        resampler = None
        if rate != SAMPLE_RATE:  # streaming, so no clicks at chunk edges
            import soxr
            resampler = soxr.ResampleStream(rate, SAMPLE_RATE, 1, dtype="float32")
        buf = np.zeros(0, np.float32)
        for chunk in mic.stream():
            x = chunk.reshape(-1).astype(np.float32)
            buf = np.concatenate([buf, resampler.resample_chunk(x) if resampler else x])
            while len(buf) >= WINDOW:
                w, buf = buf[:WINDOW], buf[WINDOW:]
                yield w


def main():
    sys.stdout.reconfigure(line_buffering=True)
    cfg = config.load(HERE / "config" / "board.yaml")
    species = config.load_species(cfg.species_file)
    cfg.log_file = str(HERE.parent / cfg.log_file)  # TODO(hardware): app folder writable from the container?

    state = State()
    ui = WebUI(port=cfg.web_port)  # serves ../assets/index.html
    # TODO(hardware): open http://<board-ip>:7000/ from the laptop; check /api/state returns JSON.
    ui.expose_api("GET", "/api/state", state.snapshot)

    classifier = BirdNetClassifier(species, cfg.min_conf)
    source = AppLabMicSource(cfg.device) if cfg.source == "applab" else make_source(cfg)
    pipeline = Pipeline(cfg, species, classifier, BridgeDisplay(), state=state, log=EventLog(cfg.log_file),
                        verbose=cfg.verbose)
    # App.run calls user_loop forever: if the mic stream ends, the pipeline restarts.
    # TODO(hardware): check Stop in App Lab ends the app while user_loop is blocked on the mic.
    App.run(user_loop=lambda: pipeline.run(source.windows(), mute=cfg.mute))


main()
