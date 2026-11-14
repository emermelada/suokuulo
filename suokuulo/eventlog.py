"""Append-only CSV event log, flushed per row so a power cut loses at most one line."""
import csv
import os

FIELDS = ["iso_time", "label", "kind", "confidence", "score", "alert"]


class EventLog:
    def __init__(self, path):
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        self.file = open(path, "a", newline="")
        self.writer = csv.writer(self.file)
        if new:
            self.write(*FIELDS)

    def write(self, iso_time, label, kind, confidence, score, alert):
        self.writer.writerow([iso_time, label, kind, confidence, score, alert])
        self.file.flush()
