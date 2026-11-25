"""
T03 — Pipeline Overhead
Dimension: Performance

Target: Time and memory per stage of NSS-EC pipeline.
  Stages: RS encode → AES-256-GCM encrypt → Shamir SSS split → upload
Method: 10 sizes × 10 reps = 100 measurements with tracemalloc profiling.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, time, secrets, tracemalloc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import rs_encode, encrypt_shard, shamir_split_key, RS_N
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 10
RUN_NUMBER = 1


def profile_one(size_mb: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    master_key = secrets.token_bytes(32)

    # Stage 1: RS encode
    tracemalloc.start()
    t0 = time.perf_counter()
    shards, padding = rs_encode(data)
    rs_ms = (time.perf_counter() - t0) * 1000
    _, rs_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Stage 2: AES-256-GCM encrypt all shards
    tracemalloc.start()
    t1 = time.perf_counter()
    nonces, enc_shards = [], []
    for i, s in enumerate(shards):
        n, ct = encrypt_shard(s, master_key, i)
        nonces.append(n)
        enc_shards.append(ct)
    aes_ms = (time.perf_counter() - t1) * 1000
    _, aes_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Stage 3: Shamir SSS split
    t2 = time.perf_counter()
    shares = shamir_split_key(master_key)
    shamir_ms = (time.perf_counter() - t2) * 1000

    total_stall_ms = rs_ms + aes_ms + shamir_ms

    return {
        "size_mb": size_mb,
        "rs_encode_ms": round(rs_ms, 2),
        "aes_encrypt_ms": round(aes_ms, 2),
        "shamir_split_ms": round(shamir_ms, 2),
        "total_stall_ms": round(total_stall_ms, 2),
        "rs_peak_mb": round(rs_peak / 1024 / 1024, 2),
        "aes_peak_mb": round(aes_peak / 1024 / 1024, 2),
        "rs_pct": round(rs_ms / total_stall_ms * 100, 1),
        "aes_pct": round(aes_ms / total_stall_ms * 100, 1),
    }


if __name__ == "__main__":
    records = []
    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T03 | {size_mb} MB | rep {rep}/{REPS}")
            r = profile_one(size_mb)
            r["rep"] = rep
            records.append(r)
            print(f"      RS={r['rs_encode_ms']}ms ({r['rs_pct']}%)  "
                  f"AES={r['aes_encrypt_ms']}ms ({r['aes_pct']}%)  "
                  f"Stall={r['total_stall_ms']}ms")

    save("T03_pipeline_overhead", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT03 complete — {len(records)} measurements saved.")
