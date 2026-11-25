"""
T16A — Unencrypted Baseline
Dimension: Performance Baseline

Target: Measure raw upload throughput with no encryption, no erasure coding.
  Establishes the ceiling throughput that NSS-EC overhead is measured against.
  Direct single-object upload to each SeaweedFS bucket.
  10 sizes × 20 reps.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.cloud_client import upload_object, download_object, ensure_buckets, ENDPOINTS, _make_client
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 20
RUN_NUMBER = 1


def run_one(size_mb: int, rep: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t16a-{size_mb}mb-rep{rep}"

    # Upload raw (no encryption) to all 3 CSPs
    t0 = time.perf_counter()
    for ep in ENDPOINTS:
        upload_object(ep, f"{file_id}/raw", data)
    upload_s = time.perf_counter() - t0

    # Download from first CSP
    t1 = time.perf_counter()
    recovered = download_object(ENDPOINTS[0], f"{file_id}/raw")
    download_s = time.perf_counter() - t1

    return {
        "size_mb": size_mb,
        "rep": rep,
        "upload_s": round(upload_s, 3),
        "download_s": round(download_s, 3),
        "upload_throughput_mb_s": round(size_mb / upload_s, 2),
        "download_throughput_mb_s": round(size_mb / download_s, 2),
        "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T16A | {size_mb} MB | rep {rep}/{REPS}")
            r = run_one(size_mb, rep)
            records.append(r)
            print(f"       up={r['upload_s']}s ({r['upload_throughput_mb_s']} MB/s)  "
                  f"down={r['download_s']}s")

    save("T16A_baseline", RUN_NUMBER, {
        "measurements": records,
        "mean_upload_throughput": round(
            sum(r["upload_throughput_mb_s"] for r in records) / len(records), 2),
    })
    print(f"\nT16A complete — {len(records)} measurements saved")
