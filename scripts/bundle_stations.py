#!/usr/bin/env python3
"""Reduce a locally downloaded, pinned Trainline CSV to the bundled GB CRS catalogue."""

import csv
import json
import re
import sys
from pathlib import Path


def bundle(source: Path, destination: Path) -> None:
    with source.open(encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle, delimiter=";")
            if row["country"] == "GB"
            and re.fullmatch(r"[A-Z]{3}", row["atoc_id"])
            and row["is_city"] != "t"
        ]
    stations = {row["atoc_id"]: row["name"] for row in rows}
    if len(stations) != len(rows):
        raise ValueError("Duplicate CRS codes require manual review")
    destination.write_text(
        json.dumps(stations, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    bundle(Path(sys.argv[1]), Path(sys.argv[2]))
