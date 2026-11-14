"""Round trip: the MCU encoder (applab/sketch/payload.h, compiled here with the
host C++ compiler) against scripts/decode_payload.py."""
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("decode_payload", ROOT / "scripts/decode_payload.py")
decode_payload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decode_payload)

PROGRAM = r"""
#include <cstdio>
#include <cstdlib>
#include "payload.h"
int main(int argc, char **argv) {
  Summary s;
  s.health = atoi(argv[3]); s.richness = atoi(argv[4]); s.activity = atoi(argv[5]);
  s.speciesMask = atoi(argv[6]); s.detections = atoi(argv[7]);
  uint8_t buf[PAYLOAD_LEN];
  size_t n = encodePayload(buf, atoi(argv[1]), atoi(argv[2]), s, strtoul(argv[8], 0, 10), atoi(argv[9]), atoi(argv[10]));
  for (size_t i = 0; i < n; i++) printf("%02x", buf[i]);
}
"""


@pytest.fixture(scope="module")
def encoder(tmp_path_factory):
    cxx = shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        pytest.skip("no C++ compiler")
    d = tmp_path_factory.mktemp("enc")
    (d / "main.cpp").write_text(PROGRAM)
    subprocess.run([cxx, "-std=c++17", "-Wall", "-Werror", "-I", str(ROOT / "applab/sketch"),
                    str(d / "main.cpp"), "-o", str(d / "enc")], check=True)
    return lambda *args: bytes.fromhex(subprocess.run([str(d / "enc"), *map(str, args)],
                                                      capture_output=True, text=True, check=True).stdout)


def test_summary_round_trip(encoder):
    mask = 0b1000_0000_0101  # golden_plover, common_snipe, black_grouse
    payload = encoder(1, 1, 73, 62, 88, mask, 1234, 90061, 0, 7)
    assert len(payload) == 16
    assert decode_payload.decode(payload) == {
        "type": "summary", "flags": ["linux_ok"], "health": 73, "richness_pct": 62, "activity_pct": 88,
        "species_heard_today": ["golden_plover", "common_snipe", "black_grouse"], "detections_today": 1234,
        "mcu_uptime_s": 90061, "min_since_linux_heartbeat": 0, "seq": 7}


def test_linux_down_without_summary(encoder):
    d = decode_payload.decode(encoder(2, 0, 255, 0, 0, 0, 0, 4000000000, 65535, 255))
    assert (d["type"], d["flags"], d["health"]) == ("linux_down", ["off_season"], None)
    assert (d["mcu_uptime_s"], d["min_since_linux_heartbeat"], d["seq"]) == (4000000000, None, 255)
