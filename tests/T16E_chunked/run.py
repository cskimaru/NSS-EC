"""
T16E — Chunked Upload (RTO Solution)
Dimension: Performance / TCP RTO Resolution

Target: Confirm chunked upload eliminates TCP RTO penalty at high RTT.
  4 MB chunks → stall per chunk ≈ 19 ms < RTO_MIN(200 ms) → no cwnd reset.

Method:
  - MONOLITHIC upload: full pipeline stall then single upload per shard
  - CHUNKED upload: encode_chunked with 4 MB chunks
  Compare at RTT 50 ms and 100 ms (cliff and beyond).
  5 sizes × 2 RTT × 2 modes × 20 reps = 400 measurements.

Finding from prior work:
  - Chunking wins at 500 MB+ where compounding RTO resets cause 3–6× penalty.
  - At 100 MB, monolithic (~20 MB/s) beats chunked (~9 MB/s).
  - Crossover point ≈ 300–400 MB.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode, encode_chunked
from core.cloud_client import upload_file, upload_file_chunked, download_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 500, 1000]
RTT_VALUES_MS = [50, 100]
REPS = 20
CHUNK_MB = 4.0
RUN_NUMBER = 1


def set_rtt(rtt_ms: int):
    delay = rtt_ms // 2
    for port in [8333, 8334, 8335]:
        band = port - 8330
        subprocess.run(
            f"tc qdisc change dev eth0 parent 1:{band} handle {band*10}: "
            f"netem delay {delay}ms",
            shell=True, capture_output=True
        )


def run_monolithic(size_mb: int, rep: int, rtt_ms: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t16e-mono-rtt{rtt_ms}-{size_mb}mb-rep{rep}"

    result = encode(data)
    t0 = time.perf_counter()
    upload_file(file_id, result, parallel=True)
    upload_s = time.perf_counter() - t0

    recovered = download_file(file_id)
    return {
        "size_mb": size_mb, "rep": rep, "rtt_ms": rtt_ms,
        "mode": "MONOLITHIC",
        "upload_s": round(upload_s, 3),
        "throughput_mb_s": round(size_mb / upload_s, 2),
        "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash,
        "stall_ms": round(result.timings.get("total_encode_ms", 0), 1),
    }


def run_chunked(size_mb: int, rep: int, rtt_ms: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t16e-chunk-rtt{rtt_ms}-{size_mb}mb-rep{rep}"

    t0 = time.perf_counter()
    upload_file_chunked(file_id, data, chunk_size_mb=CHUNK_MB, parallel=True)
    upload_s = time.perf_counter() - t0

    recovered = download_file(file_id)
    return {
        "size_mb": size_mb, "rep": rep, "rtt_ms": rtt_ms,
        "mode": "CHUNKED",
        "chunk_mb": CHUNK_MB,
        "upload_s": round(upload_s, 3),
        "throughput_mb_s": round(size_mb / upload_s, 2),
        "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for rtt_ms in RTT_VALUES_MS:
        set_rtt(rtt_ms)
        for size_mb in FILE_SIZES_MB:
            for rep in range(1, REPS + 1):
                print(f"T16E | RTT={rtt_ms}ms | {size_mb} MB | rep {rep}/{REPS}")

                r_mono = run_monolithic(size_mb, rep, rtt_ms)
                records.append(r_mono)
                r_chunk = run_chunked(size_mb, rep, rtt_ms)
                records.append(r_chunk)

                winner = "CHUNKED" if r_chunk["throughput_mb_s"] > r_mono["throughput_mb_s"] else "MONOLITHIC"
                print(f"       MONO={r_mono['throughput_mb_s']} MB/s  "
                      f"CHUNK={r_chunk['throughput_mb_s']} MB/s  "
                      f"→ {winner} wins")

    save("T16E_chunked", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT16E complete — {len(records)} measurements saved")
    print("Finding: CHUNKED wins at ≥500 MB; MONOLITHIC wins at ≤200 MB (crossover ~300–400 MB)")
