"""
Results saving utility — append-only JSON records per test run.
Every test writes raw measurements here. Never overwrite.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import json
import os
import time
import platform
import socket
from pathlib import Path
from datetime import datetime, timezone

RESULTS_DIR = Path(__file__).parent.parent / "results"


def save(test_id: str, run_number: int, data: dict):
    """
    Save a result record to results/<test_id>/run_<n>.json
    Adds environment metadata automatically.
    """
    out_dir = RESULTS_DIR / test_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"run_{run_number:02d}.json"

    record = {
        "test_id": test_id,
        "run_number": run_number,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "infrastructure": "SeaweedFS-3node",
            "note": "All results on SeaweedFS. Not comparable to prior MinIO results.",
        },
        **data,
    }

    with open(path, "w") as f:
        json.dump(record, f, indent=2)

    print(f"  Saved → {path}")
    return path


def load_all(test_id: str) -> list[dict]:
    """Load all run records for a test."""
    out_dir = RESULTS_DIR / test_id
    records = []
    for p in sorted(out_dir.glob("run_*.json")):
        with open(p) as f:
            records.append(json.load(f))
    return records
