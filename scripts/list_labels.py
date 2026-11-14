"""Print exact BirdNET v2.4 label strings for our indicator species and every
non-species label (where scientific name == common name, e.g. "Engine_Engine").

Usage: python scripts/list_labels.py
"""
import importlib.util
from pathlib import Path

INDICATORS = ["Pluvialis apricaria", "Tringa glareola", "Gallinago gallinago", "Numenius arquata",
              "Numenius phaeopus", "Anthus pratensis", "Motacilla flava", "Grus grus"]

pkg = Path(importlib.util.find_spec("birdnetlib").submodule_search_locations[0])
labels = (pkg / "models/analyzer/BirdNET_GLOBAL_6K_V2.4_Labels.txt").read_text().splitlines()
print(f"{len(labels)} labels in model")

print("\nIndicators:")
for sci in INDICATORS:
    found = [l for l in labels if l.split("_")[0] == sci]
    print(f"  {sci:22s} -> {found if found else 'MISSING'}")

print("\nNon-species labels (scientific == common):")
for l in labels:
    sci, common = l.split("_", 1)
    if sci == common:
        print(f"  {l}")
