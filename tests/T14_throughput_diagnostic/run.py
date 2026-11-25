"""
T14 — Throughput Diagnostic
Dimension: Performance

Target: Full upload + download throughput at scale (100MB–1000MB).
  Measure end-to-end time, effective throughput, stall time (encode only).
  Compare parallel vs sequential upload modes.
  10 sizes × 20 reps × 2 modes = 400 measurements.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, download_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 20
RUN_NUMBER = 1


def run_one(size_mb: int, rep: int, parallel: bool) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t14-{size_mb}mb-rep{rep}-{'par' if parallel else 'seq'}"

    # Encode (stall)
    t0 = time.perf_counter()
    result = encode(data, profile=True)
    encode_s = time.perf_counter() - t0

    # Upload
    t1 = time.perf_counter()
    upload_file(file_id, result, parallel=parallel)
    upload_s = time.perf_counter() - t1

    # Download
    t2 = time.perf_counter()
    recovered = download_file(file_id)
    download_s = time.perf_counter() - t2

    total_s = encode_s + upload_s
    return {
        "size_mb": size_mb,
        "rep": rep,
        "parallel": parallel,
        "encode_ms": round(encode_s * 1000, 1),
        "upload_s": round(upload_s, 3),
        "download_s": round(download_s, 3),
        "total_s": round(total_s, 3),
        "upload_throughput_mb_s": round(size_mb / upload_s, 2),
        "download_throughput_mb_s": round(size_mb / download_s, 2),
        "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash,
        "timings": result.timings,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for parallel in [True, False]:
        for size_mb in FILE_SIZES_MB:
            for rep in range(1, REPS + 1):
                mode = "parallel" if parallel else "sequential"
                print(f"T14 | {size_mb} MB | rep {rep}/{REPS} | {mode}")
                r = run_one(size_mb, rep, parallel)
                records.append(r)
                print(f"      encode={r['encode_ms']}ms  up={r['upload_s']}s  "
                      f"down={r['download_s']}s  "
                      f"tput={r['upload_throughput_mb_s']} MB/s")

    save("T14_throughput_diagnostic", RUN_NUMBER, {
        "measurements": records,
        "total": len(records),
    })
    print(f"\nT14 complete — {len(records)} measurements saved")
