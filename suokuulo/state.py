"""Thread-safe snapshot of pipeline state for the dashboard, plus RAM figures."""
import threading
import time
from datetime import datetime


def memory() -> dict | None:
    """Board RAM in use (/proc/meminfo: MemTotal - MemAvailable) and this app's
    resident size (/proc/self/status VmRSS), in MB. None off Linux."""
    try:
        with open("/proc/meminfo") as f:
            info = dict(line.split(":", 1) for line in f)
        with open("/proc/self/status") as f:
            status = dict(line.split(":", 1) for line in f if ":" in line)
    except OSError:
        return None

    def mb(value):
        return round(int(value.split()[0]) / 1024)  # values are in kB

    total = mb(info["MemTotal"])
    return {"used_mb": total - mb(info["MemAvailable"]), "total_mb": total, "app_mb": mb(status["VmRSS"])}


class State:
    def __init__(self, site_name="", tz=None, stale_s=15):
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.site, self.tz, self.stale_s = site_name, tz, stale_s
        self.data, self.inference_ms, self.last_window = {}, None, None

    def update(self, data, inference_ms=None):
        """New soundscape snapshot; inference_ms marks a processed audio window."""
        with self.lock:
            self.data = data
            if inference_ms is not None:
                self.inference_ms, self.last_window = round(inference_ms), time.monotonic()

    def snapshot(self) -> dict:
        with self.lock:
            data, inference_ms, last = self.data, self.inference_ms, self.last_window
        now = time.monotonic()
        if last is not None and now - last < self.stale_s:
            status = "listening"
        elif last is None and now - self.started < 30:
            status = "starting"
        else:  # no audio window for stale_s: the mic stream stopped
            status = "mic error"
        return {**data, "site": self.site, "status": status, "time": datetime.now(self.tz).strftime("%H:%M"),
                "uptime_s": round(now - self.started), "inference_ms": inference_ms, "ram": memory()}
