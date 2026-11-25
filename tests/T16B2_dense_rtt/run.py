"""
T16B2 — Dense RTT Sweep (40–60 ms)
Dimension: Performance / TCP RTO Interaction

Target: Zoom into the 40–60 ms RTT zone at 1 ms resolution.
  Confirm cliff location: stall(100MB) ≈ 487 ms > RTO_MIN(200 ms) → reset at ~50ms RTT.
  21 RTT values × 5 sizes × 10 reps.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, download_file, ensure_buckets
from core.results import save

RTT_VALUES_MS = list(range(40, 61))  # 40,41,...,60
FILE_SIZES_MB = [100, 200, 300, 400, 500]
REPS = 10
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


def run_one(size_mb: int, rep: int, rtt_ms: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t16b2-rtt{rtt_ms}-{size_mb}mb-rep{rep}"

    result = encode(data)

    t0 = time.perf_counter()
    upload_file(file_id, result, parallel=True)
    upload_s = time.perf_counter() - t0

    recovered = download_file(file_id)

    return {
        "size_mb": size_mb,
        "rep": rep,
        "rtt_ms": rtt_ms,
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
                print(f"T16B2 | RTT={rtt_ms}ms | {size_mb} MB | rep {rep}/{REPS}")
                r = run_one(size_mb, rep, rtt_ms)
                records.append(r)
                print(f"        upload={r['upload_s']}s  tput={r['throughput_mb_s']} MB/s")

    save("T16B2_dense_rtt", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT16B2 complete — {len(records)} measurements saved")
