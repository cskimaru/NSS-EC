"""
T16B3 — Straddle Zone (49–51 ms, 0.1 ms resolution)
Dimension: Performance / TCP RTO Interaction

Target: Pinpoint exact RTT where cwnd reset occurs.
  Test RTT 49.0–51.0 ms at 0.1 ms steps = 21 values.
  10 reps each for 100 MB only (fastest measurement).

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, ensure_buckets
from core.results import save

RTT_VALUES_MS = [round(49.0 + i * 0.1, 1) for i in range(21)]  # 49.0–51.0
FILE_SIZE_MB = 100
REPS = 10
RUN_NUMBER = 1


def set_rtt_precise(rtt_ms: float):
    """Set tc netem RTT with 0.1 ms precision (netem accepts float ms)."""
    delay_ms = rtt_ms / 2
    for port in [8333, 8334, 8335]:
        band = port - 8330
        subprocess.run(
            f"tc qdisc change dev eth0 parent 1:{band} handle {band*10}: "
            f"netem delay {delay_ms:.1f}ms",
            shell=True, capture_output=True
        )


def run_one(rep: int, rtt_ms: float) -> dict:
    data = secrets.token_bytes(FILE_SIZE_MB * 1024 * 1024)
    file_id = f"t16b3-rtt{rtt_ms}-rep{rep}"

    result = encode(data)

    t0 = time.perf_counter()
    upload_file(file_id, result, parallel=True)
    upload_s = time.perf_counter() - t0

    return {
        "size_mb": FILE_SIZE_MB,
        "rep": rep,
        "rtt_ms": rtt_ms,
        "upload_s": round(upload_s, 3),
        "throughput_mb_s": round(FILE_SIZE_MB / upload_s, 2),
        "stall_ms": round(result.timings.get("total_encode_ms", 0), 1),
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for rtt_ms in RTT_VALUES_MS:
        set_rtt_precise(rtt_ms)
        for rep in range(1, REPS + 1):
            print(f"T16B3 | RTT={rtt_ms}ms | rep {rep}/{REPS}")
            r = run_one(rep, rtt_ms)
            records.append(r)
            print(f"        upload={r['upload_s']}s  tput={r['throughput_mb_s']} MB/s")

    save("T16B3_straddle", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT16B3 complete — {len(records)} measurements saved")
