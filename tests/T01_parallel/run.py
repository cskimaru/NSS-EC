"""
T01 — Throughput: Parallel vs Sequential Transfer
Dimension: Performance

Target: Show parallel upload of 9 shards is significantly faster than sequential.
Method: 10 file sizes × 20 reps × 2 modes (sequential, parallel) = 400 measurements.
Expected: Parallel wins. Set as standard for all subsequent tests.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, time, hashlib, secrets
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 20
RUN_NUMBER = 1  # increment for each fresh run

def run_one(size_mb: int, parallel: bool, rep: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    file_id = f"t01-{size_mb}mb-{'par' if parallel else 'seq'}-rep{rep}"

    t0 = time.perf_counter()
    result = encode(data)
    encode_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    timings = upload_file(file_id, result, parallel=parallel)
    upload_s = time.perf_counter() - t1

    total_s = (time.perf_counter() - t0)
    throughput = size_mb / total_s

    return {
        "size_mb": size_mb,
        "mode": "parallel" if parallel else "sequential",
        "rep": rep,
        "encode_ms": round(encode_ms, 2),
        "upload_s": round(upload_s, 3),
        "total_s": round(total_s, 3),
        "throughput_mb_s": round(throughput, 2),
        "csp_timings": timings,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []
    for size_mb in FILE_SIZES_MB:
        for mode, parallel in [("sequential", False), ("parallel", True)]:
            for rep in range(1, REPS + 1):
                print(f"T01 | {size_mb} MB | {mode} | rep {rep}/{REPS}")
                r = run_one(size_mb, parallel, rep)
                records.append(r)
                print(f"      throughput={r['throughput_mb_s']} MB/s  upload={r['upload_s']}s")

    save("T01_parallel", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT01 complete — {len(records)} measurements saved.")
