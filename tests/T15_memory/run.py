"""
T15 — Memory Profiling
Dimension: Resource Utilisation

Target: Peak RSS and tracemalloc peak per stage and file size.
  Identify memory bottleneck (RS encode creates n/k × file_size in buffers).
  10 sizes × 10 reps (no cloud upload — CPU/RAM only).

Expected:
  Peak RSS ≈ 2.5× file_size (input + RS matrix + 9 shards).
  Dominant stage: RS encode.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, tracemalloc, time
import psutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import rs_encode, encrypt_shard, shamir_split_key, RS_N
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 10
RUN_NUMBER = 1

proc = psutil.Process(os.getpid())


def run_one(size_mb: int, rep: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    master_key = secrets.token_bytes(32)
    rss_before = proc.memory_info().rss

    # RS encode
    tracemalloc.start()
    t0 = time.perf_counter()
    shards, padding = rs_encode(data)
    rs_ms = (time.perf_counter() - t0) * 1000
    _, rs_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after_rs = proc.memory_info().rss

    # AES encrypt
    tracemalloc.start()
    t1 = time.perf_counter()
    enc_shards = []
    nonces = []
    for i, s in enumerate(shards):
        n, ct = encrypt_shard(s, master_key, i)
        nonces.append(n)
        enc_shards.append(ct)
    aes_ms = (time.perf_counter() - t1) * 1000
    _, aes_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after_aes = proc.memory_info().rss

    # Shamir
    t2 = time.perf_counter()
    shares = shamir_split_key(master_key)
    shamir_ms = (time.perf_counter() - t2) * 1000

    rss_peak = proc.memory_info().rss

    # Cleanup
    del data, shards, enc_shards

    return {
        "size_mb": size_mb,
        "rep": rep,
        "rs_encode_ms": round(rs_ms, 1),
        "aes_ms": round(aes_ms, 1),
        "shamir_ms": round(shamir_ms, 2),
        "rs_tracemalloc_peak_mb": round(rs_peak / 1024 / 1024, 2),
        "aes_tracemalloc_peak_mb": round(aes_peak / 1024 / 1024, 2),
        "rss_before_mb": round(rss_before / 1024 / 1024, 1),
        "rss_after_rs_mb": round(rss_after_rs / 1024 / 1024, 1),
        "rss_after_aes_mb": round(rss_after_aes / 1024 / 1024, 1),
        "rss_peak_mb": round(rss_peak / 1024 / 1024, 1),
        "rss_overhead_ratio": round((rss_peak - rss_before) / (size_mb * 1024 * 1024), 2),
    }


if __name__ == "__main__":
    records = []
    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T15 | {size_mb} MB | rep {rep}/{REPS}")
            r = run_one(size_mb, rep)
            records.append(r)
            print(f"      RS={r['rs_encode_ms']}ms  AES={r['aes_ms']}ms  "
                  f"RSS_peak={r['rss_peak_mb']} MB  "
                  f"overhead={r['rss_overhead_ratio']}×")

    save("T15_memory", RUN_NUMBER, {
        "measurements": records,
        "mean_rss_overhead": round(sum(r["rss_overhead_ratio"] for r in records) / len(records), 3),
    })
    print(f"\nT15 complete — {len(records)} measurements saved")
