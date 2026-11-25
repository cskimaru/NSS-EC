"""
T16C — Batch vs. Stream Upload
Dimension: Performance

Target: Compare uploading a batch of small files vs. a single large file.
  Batch: N × 10 MB files uploaded concurrently.
  Stream: 1 × (N×10) MB file uploaded as monolith.
  5 batch sizes × 10 reps each.

Expected: Batch shows better parallelism for small files;
  monolith wins at large sizes (less per-file overhead).

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time
import concurrent.futures
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, ensure_buckets
from core.results import save

BATCH_SIZES = [5, 10, 20, 50, 100]  # N files of 10 MB each
FILE_UNIT_MB = 10
REPS = 10
RUN_NUMBER = 1


def upload_one(idx: int, batch_id: str) -> float:
    data = secrets.token_bytes(FILE_UNIT_MB * 1024 * 1024)
    result = encode(data)
    t0 = time.perf_counter()
    upload_file(f"{batch_id}-f{idx}", result, parallel=True)
    return time.perf_counter() - t0


def run_batch(n_files: int, rep: int) -> dict:
    batch_id = f"t16c-n{n_files}-rep{rep}"
    total_mb = n_files * FILE_UNIT_MB

    # Batch upload
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n_files, 8)) as ex:
        list(ex.map(lambda i: upload_one(i, batch_id), range(n_files)))
    batch_s = time.perf_counter() - t0

    # Monolith upload (same total size)
    data_mono = secrets.token_bytes(total_mb * 1024 * 1024)
    result_mono = encode(data_mono)
    t1 = time.perf_counter()
    upload_file(f"{batch_id}-mono", result_mono, parallel=True)
    mono_s = time.perf_counter() - t1

    return {
        "n_files": n_files,
        "rep": rep,
        "total_mb": total_mb,
        "batch_upload_s": round(batch_s, 3),
        "mono_upload_s": round(mono_s, 3),
        "batch_throughput_mb_s": round(total_mb / batch_s, 2),
        "mono_throughput_mb_s": round(total_mb / mono_s, 2),
        "batch_wins": batch_s < mono_s,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for n_files in BATCH_SIZES:
        for rep in range(1, REPS + 1):
            print(f"T16C | {n_files} files × {FILE_UNIT_MB} MB | rep {rep}/{REPS}")
            r = run_batch(n_files, rep)
            records.append(r)
            print(f"       batch={r['batch_upload_s']}s ({r['batch_throughput_mb_s']} MB/s)  "
                  f"mono={r['mono_upload_s']}s ({r['mono_throughput_mb_s']} MB/s)  "
                  f"{'batch wins' if r['batch_wins'] else 'mono wins'}")

    save("T16C_batch_vs_stream", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT16C complete — {len(records)} measurements saved")
