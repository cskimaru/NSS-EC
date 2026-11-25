"""
T13 — Cascading Failure (Two CSPs Offline)
Dimension: Availability / Failure Boundary

Target: Prove NSS-EC CANNOT reconstruct when 2 of 3 CSPs are offline.
  RS threshold k=6 requires shards from at least 2 CSPs.
  Shamir threshold k=2 requires shares from at least 2 CSPs.
  With only 1 CSP available: 3 shards < 6 AND only 1 share < 2 → catastrophic loss.
  System must correctly report failure, not silently return corrupted data.
  10 sizes × 10 reps × 3 single-CSP scenarios.

Expected: 100% failure-detected, 0% silent data corruption.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, download_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 10
RUN_NUMBER = 1


def run_one(size_mb: int, rep: int, only_csp: int) -> dict:
    """Attempt recovery with only one CSP available."""
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t13-{size_mb}mb-rep{rep}"

    result = encode(data)
    upload_file(file_id, result, parallel=True)

    # Attempt download with only 1 CSP
    failure_detected = False
    silent_corruption = False

    try:
        recovered = download_file(file_id, available_csps=[only_csp])
        # If we got here, check if it's corrupted
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        if recovered_hash == orig_hash:
            # Correctly reconstructed with 1 CSP — this should NOT happen
            failure_detected = False
            silent_corruption = False
        else:
            # Returned wrong data silently — DANGEROUS
            silent_corruption = True
            failure_detected = False
    except Exception:
        # Correctly detected unrecoverable failure
        failure_detected = True
        silent_corruption = False

    return {
        "size_mb": size_mb,
        "rep": rep,
        "only_csp": only_csp,
        "failure_detected": failure_detected,
        "silent_corruption": silent_corruption,
        "correct_behaviour": failure_detected and not silent_corruption,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []
    correct_count = 0

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            for only_csp in range(3):
                print(f"T13 | {size_mb} MB | rep {rep} | only CSP{only_csp}")
                r = run_one(size_mb, rep, only_csp)
                records.append(r)
                if r["correct_behaviour"]:
                    correct_count += 1
                print(f"      failure_detected={r['failure_detected']}  "
                      f"silent_corrupt={r['silent_corruption']}  "
                      f"{'PASS' if r['correct_behaviour'] else 'FAIL'}")

    total = len(records)
    save("T13_cascading_failure", RUN_NUMBER, {
        "measurements": records,
        "correct_behaviour_pct": round(correct_count / total * 100, 2),
    })
    print(f"\nT13 complete — correct failure detection in {correct_count}/{total} trials")
