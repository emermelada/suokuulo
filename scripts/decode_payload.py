"""Decode a SuoKuulo LoRa uplink payload (16 bytes, see applab/sketch/payload.h).

Usage: python scripts/decode_payload.py 1101...  (hex, as printed on the MCU serial
or delivered by the LoRa network server)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from suokuulo.config import load_species  # noqa: E402

TYPES = {1: "summary", 2: "linux_down", 3: "heartbeat", 4: "recovered"}
FLAGS = {1: "linux_ok", 2: "off_season"}
SPECIES = Path(__file__).resolve().parents[1] / "config/species.yaml"


def decode(payload: bytes, species_file=SPECIES) -> dict:
    if len(payload) != 16:
        raise ValueError(f"expected 16 bytes, got {len(payload)}")
    head, flags, health, richness, activity, mask, detections, uptime, since, seq = \
        struct.unpack("<BBBBBHHIHB", payload)
    if head >> 4 != 1:
        raise ValueError(f"unknown payload version {head >> 4}")
    indicators = [s.id for s in load_species(species_file) if s.kind == "indicator"]
    return {"type": TYPES.get(head & 0x0f, f"unknown {head & 0x0f}"),
            "flags": [name for bit, name in FLAGS.items() if flags & bit],
            "health": None if health == 255 else health, "richness_pct": richness, "activity_pct": activity,
            "species_heard_today": [sid for i, sid in enumerate(indicators) if mask >> i & 1],
            "detections_today": detections, "mcu_uptime_s": uptime,
            "min_since_linux_heartbeat": None if since == 65535 else since, "seq": seq}


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        for k, v in decode(bytes.fromhex(arg)).items():
            print(f"{k:26s} {v}")
