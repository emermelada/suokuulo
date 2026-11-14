"""Audio sources. Every source yields float32 mono windows of 3.0 s at 48 kHz."""
import subprocess
import time
from pathlib import Path
from typing import Iterator, Protocol

import numpy as np

SAMPLE_RATE = 48000
WINDOW = 3 * SAMPLE_RATE  # 144000 samples
AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac"}


class AudioSource(Protocol):
    sample_rate: int
    def windows(self) -> Iterator[np.ndarray]: ...


def split_windows(y: np.ndarray) -> Iterator[np.ndarray]:
    """Cut a 48 kHz mono signal into 3 s windows, zero-padding the last one."""
    for i in range(0, max(len(y), 1), WINDOW):
        w = np.zeros(WINDOW, np.float32)
        chunk = y[i:i + WINDOW]
        w[:len(chunk)] = chunk
        yield w


def resample(y: np.ndarray, rate: int) -> np.ndarray:
    """To 48 kHz with soxr (what librosa uses inside, without librosa's ~70 MB of imports)."""
    if rate == SAMPLE_RATE:
        return y
    import soxr
    return soxr.resample(y, rate, SAMPLE_RATE)


def load_audio(path) -> np.ndarray:
    """WAV/FLAC/OGG/MP3 (libsndfile) as 48 kHz mono float32."""
    import soundfile as sf
    y, rate = sf.read(path, dtype="float32", always_2d=True)
    return resample(y.mean(axis=1), rate)


def audio_files(folder_or_file) -> list[Path]:
    p = Path(folder_or_file)
    if p.is_file():
        return [p]
    return sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXT)


class FileSource:
    sample_rate = SAMPLE_RATE

    def __init__(self, folder_or_file, loop=False, realtime=False):
        self.files = audio_files(folder_or_file)
        if not self.files:
            raise FileNotFoundError(f"no audio files in {folder_or_file}")
        self.loop, self.realtime = loop, realtime

    def windows(self):
        next_t = time.monotonic()
        while True:
            for f in self.files:
                for w in split_windows(load_audio(f)):
                    if self.realtime:  # pace like a live mic: one window per 3 s
                        next_t += WINDOW / SAMPLE_RATE
                        time.sleep(max(0.0, next_t - time.monotonic()))
                    yield w
            if not self.loop:
                return


class MicSource:
    """Live capture. backend "sounddevice" (PortAudio) or "arecord" (ALSA CLI fallback)."""
    sample_rate = SAMPLE_RATE

    def __init__(self, device=None, backend="sounddevice"):
        self.device, self.backend = device, backend

    def windows(self):
        if self.backend == "arecord":
            cmd = ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "48000", "-c", "1"]
            if self.device is not None:
                cmd += ["-D", str(self.device)]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            try:
                while len(buf := proc.stdout.read(WINDOW * 2)) == WINDOW * 2:
                    yield np.frombuffer(buf, np.int16).astype(np.float32) / 32768
                raise RuntimeError(f"arecord exited with code {proc.wait()}")
            finally:
                proc.terminate()
                proc.wait()
        import sounddevice as sd
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.device) as stream:
            while True:
                data, overflowed = stream.read(WINDOW)
                if overflowed:
                    print("[mic] input overflow: inference slower than real time?")
                yield data[:, 0].copy()


def make_source(cfg) -> AudioSource:
    if cfg.source == "file":
        return FileSource(cfg.input, loop=cfg.loop, realtime=cfg.realtime)
    if cfg.source in ("mic", "arecord"):
        return MicSource(cfg.device, backend="arecord" if cfg.source == "arecord" else "sounddevice")
    raise ValueError(f"unknown audio source {cfg.source!r}")
