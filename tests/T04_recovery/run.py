"""
T04 — One-Cloud Offline Recovery
Dimension: Availability

Target: 100% master-key and data recovery with one CSP offline.
Method: Upload to all 3. Simulate each CSP offline in turn. Recover from 2.
  10 sizes × 10 reps × 3 failure scenarios = 300 measurements.
Expected: 100% SHA-256 hash match. Shamir k=2 threshold confirmed.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, time, hashlib, secrets
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, download_file, ensure_buckets, NUM_CSP
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 10
RUN_NUMBER = 1


def run_one(size_mb: int, rep: int, offline_csp: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t04-{size_mb}mb-rep{rep}"

    result = encode(data)
    upload_file(file_id, result, parallel=True)

    # Recover using the other 2 CSPs only
    available = [i for i in range(NUM_CSP) if i != offline_csp]

    t0 = time.perf_counter()
    recovered = download_file(file_id, available_csps=available)
    recovery_s = time.perf_counter() - t0

    recovered_hash = hashlib.sha256(recovered).hexdigest()
    return {
        "size_mb": size_mb,
        "rep": rep,
        "offline_csp": offline_csp,
        "available_csps": available,
        "recovery_s": round(recovery_s, 3),
        "hash_match": recovered_hash == orig_hash,
        "recovered_hash": recovered_hash,
        "original_hash": orig_hash,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []
    success = 0

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            for offline_csp in range(NUM_CSP):
                print(f"T04 | {size_mb} MB | rep {rep} | CSP{offline_csp} offline")
                r = run_one(size_mb, rep, offline_csp)
                records.append(r)
                if r["hash_match"]:
                    success += 1
                print(f"      hash_match={r['hash_match']}  recovery={r['recovery_s']}s")

    total = len(records)
    save("T04_recovery", RUN_NUMBER, {
        "measurements": records,
        "total": total,
        "success_rate_pct": round(success / total * 100, 2),
    })
    print(f"\nT04 complete — {success}/{total} successful recoveries ({success/total*100:.1f}%)")
