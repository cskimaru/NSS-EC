"""
T16D — RTO Fix: BBR + BDP Tuning
Dimension: Performance / TCP Optimisation

Target: Measure throughput improvement from:
  (a) Default Linux TCP (cubic, 4 KB buffers)
  (b) BBR + BDP-tuned buffers (128 MB, tcp_no_metrics_save)
  At RTT 50 ms (at the cliff) and 100 ms, file sizes 100–500 MB.

Method: Apply sysctl tuning via tc_netem.sh tcp command.
  Compare before/after for each condition.
  5 sizes × 2 RTT × 2 modes × 10 reps = 200 measurements.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, download_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500]
RTT_VALUES_MS = [50, 100]
REPS = 10
RUN_NUMBER = 1

INFRA_DIR = os.path.join(os.path.dirname(__file__), "../../infra")


def set_rtt(rtt_ms: int):
    delay = rtt_ms // 2
    for port in [8333, 8334, 8335]:
        band = port - 8330
        subprocess.run(
            f"tc qdisc change dev eth0 parent 1:{band} handle {band*10}: "
            f"netem delay {delay}ms",
            shell=True, capture_output=True
        )


def apply_bbr():
    """Apply BBR + BDP sysctl tuning."""
    subprocess.run(
        f"bash {INFRA_DIR}/tc_netem.sh tcp",
        shell=True, check=True
    )


def reset_to_cubic():
    """Reset congestion control to cubic (Linux default)."""
    subprocess.run(
        "sysctl -w net.ipv4.tcp_congestion_control=cubic "
        "net.core.rmem_max=212992 net.core.wmem_max=212992",
        shell=True, capture_output=True
    )


def run_one(size_mb: int, rep: int, rtt_ms: int, bbr: bool) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t16d-rtt{rtt_ms}-{size_mb}mb-rep{rep}-{'bbr' if bbr else 'cubic'}"

    result = encode(data)

    t0 = time.perf_counter()
    upload_file(file_id, result, parallel=True)
    upload_s = time.perf_counter() - t0

    recovered = download_file(file_id)

    return {
        "size_mb": size_mb,
        "rep": rep,
        "rtt_ms": rtt_ms,
        "bbr": bbr,
        "upload_s": round(upload_s, 3),
        "throughput_mb_s": round(size_mb / upload_s, 2),
        "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for rtt_ms in RTT_VALUES_MS:
        set_rtt(rtt_ms)
        for bbr in [False, True]:
            if bbr:
                apply_bbr()
            else:
                reset_to_cubic()

            for size_mb in FILE_SIZES_MB:
                for rep in range(1, REPS + 1):
                    mode = "BBR+BDP" if bbr else "Cubic"
                    print(f"T16D | RTT={rtt_ms}ms | {mode} | {size_mb} MB | rep {rep}/{REPS}")
                    r = run_one(size_mb, rep, rtt_ms, bbr)
                    records.append(r)
                    print(f"       upload={r['upload_s']}s  tput={r['throughput_mb_s']} MB/s")

    save("T16D_rto_fix", RUN_NUMBER, {"measurements": records, "total": len(records)})
    print(f"\nT16D complete — {len(records)} measurements saved")
