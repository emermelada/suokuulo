"""Audio sources. Every source yields float32 mono windows of 3.0 s at 48 kHz,
one every hop_s seconds (hop_s < 3 overlaps them)."""
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


def split_windows(y: np.ndarray, hop=WINDOW) -> Iterator[np.ndarray]:
    """Cut a 48 kHz mono signal into 3 s windows every hop samples, zero-padding the last one."""
    for i in range(0, max(len(y) - WINDOW + hop, 1), hop):
        w = np.zeros(WINDOW, np.float32)
        chunk = y[i:i + WINDOW]
        w[:len(chunk)] = chunk
        yield w


def rechunk(chunks, hop=WINDOW) -> Iterator[np.ndarray]:
    """A live stream of float32 chunks of any size -> 3 s windows every hop samples."""
    buf = np.zeros(0, np.float32)
    for c in chunks:
        buf = np.concatenate([buf, c])
        while len(buf) >= WINDOW:
            yield buf[:WINDOW]
            buf = buf[hop:]


def highpass_gain(hz, n=WINDOW, order=2):
    """Butterworth-shaped magnitude (12 dB/octave at order 2) for np.fft.rfft of n
    samples. Applied in the frequency domain it is zero-phase and needs no scipy."""
    f = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    with np.errstate(divide="ignore"):
        return 1 / np.sqrt(1 + (hz / f) ** (2 * order))


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

    def __init__(self, folder_or_file, loop=False, realtime=False, hop_s=3.0):
        self.files = audio_files(folder_or_file)
        if not self.files:
            raise FileNotFoundError(f"no audio files in {folder_or_file}")
        self.loop, self.realtime, self.hop = loop, realtime, int(hop_s * SAMPLE_RATE)

    def windows(self):
        next_t = time.monotonic()
        while True:
            for f in self.files:
                for w in split_windows(load_audio(f), self.hop):
                    if self.realtime:  # pace like a live mic: one window per hop
                        next_t += self.hop / SAMPLE_RATE
                        time.sleep(max(0.0, next_t - time.monotonic()))
                    yield w
            if not self.loop:
                return


class MicSource:
    """Live capture. backend "sounddevice" (PortAudio) or "arecord" (ALSA CLI fallback)."""
    sample_rate = SAMPLE_RATE

    def __init__(self, device=None, backend="sounddevice", hop_s=3.0):
        self.device, self.backend, self.hop = device, backend, int(hop_s * SAMPLE_RATE)

    def windows(self):
        yield from rechunk(self.arecord() if self.backend == "arecord" else self.sounddevice(), self.hop)

    def arecord(self):
        cmd = ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "48000", "-c", "1"]
        if self.device is not None:
            cmd += ["-D", str(self.device)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        try:
            while len(buf := proc.stdout.read(self.hop * 2)) == self.hop * 2:
                yield np.frombuffer(buf, np.int16).astype(np.float32) / 32768
            raise RuntimeError(f"arecord exited with code {proc.wait()}")
        finally:
            proc.terminate()
            proc.wait()

    def sounddevice(self):
        import sounddevice as sd
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.device) as stream:
            while True:
                data, overflowed = stream.read(self.hop)
                if overflowed:
                    print("[mic] input overflow: inference slower than real time?")
                yield data[:, 0].copy()


def make_source(cfg) -> AudioSource:
    if cfg.source == "file":
        return FileSource(cfg.input, loop=cfg.loop, realtime=cfg.realtime, hop_s=cfg.hop_s)
    if cfg.source in ("mic", "arecord"):
        return MicSource(cfg.device, backend="arecord" if cfg.source == "arecord" else "sounddevice", hop_s=cfg.hop_s)
    raise ValueError(f"unknown audio source {cfg.source!r}")
