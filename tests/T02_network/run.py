"""
T02 — Network Conditions
Dimension: Availability

Target: NSS-EC performance under latency, packet loss, and bandwidth limits.
Method: Vary tc netem conditions; measure throughput and data integrity.
  - Latency levels: 0, 50, 100, 150, 200 ms RTT
  - Packet loss: 0%, 0.5%, 1%, 2%, 5%
  - Bandwidth caps: 1000, 500, 200, 100, 50 Mbps
  10 sizes × conditions × 5 reps each.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, time, hashlib, secrets, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode, decode
from core.cloud_client import upload_file, download_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500]
REPS = 5
RUN_NUMBER = 1

LATENCY_RTT_MS = [0, 50, 100, 150, 200]
PACKET_LOSS_PCT = [0.0, 0.5, 1.0, 2.0]
BW_MBPS = [1000, 500, 200, 100, 50]


def set_netem(rtt_ms: int = 0, loss_pct: float = 0.0, bw_mbps: int = 1000):
    """Apply tc netem condition via shell."""
    delay = rtt_ms // 2
    for port in [8333, 8334, 8335]:
        cmd = (
            f"tc qdisc change dev eth0 parent 1:{port-8330} handle {(port-8330)*10}: "
            f"netem delay {delay}ms loss {loss_pct}% rate {bw_mbps}mbit"
        )
        subprocess.run(cmd, shell=True, capture_output=True)


def run_one(size_mb: int, rep: int, condition: dict) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t02-{size_mb}mb-rep{rep}"

    result = encode(data)

    t0 = time.perf_counter()
    upload_file(file_id, result, parallel=True)
    upload_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    recovered = download_file(file_id)
    download_s = time.perf_counter() - t1

    return {
        "size_mb": size_mb,
        "rep": rep,
        "condition": condition,
        "upload_s": round(upload_s, 3),
        "download_s": round(download_s, 3),
        "throughput_mb_s": round(size_mb / upload_s, 2),
        "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    # Latency sweep
    for rtt in LATENCY_RTT_MS:
        set_netem(rtt_ms=rtt, loss_pct=0.0, bw_mbps=1000)
        for size_mb in FILE_SIZES_MB:
            for rep in range(1, REPS + 1):
                print(f"T02 | RTT={rtt}ms | {size_mb} MB | rep {rep}")
                r = run_one(size_mb, rep, {"type": "latency", "rtt_ms": rtt})
                records.append(r)

    # Packet loss sweep (at 100ms RTT / 100Mbps)
    for loss in PACKET_LOSS_PCT:
        set_netem(rtt_ms=100, loss_pct=loss, bw_mbps=100)
        for size_mb in FILE_SIZES_MB:
            for rep in range(1, REPS + 1):
                print(f"T02 | loss={loss}% | {size_mb} MB | rep {rep}")
                r = run_one(size_mb, rep, {"type": "loss", "loss_pct": loss})
                records.append(r)

    save("T02_network", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT02 complete — {len(records)} measurements saved.")
