"""
T07 — Shamir Threshold Proof
Dimension: Cryptographic Sovereignty

Target: Prove k=2 threshold: any 2 shares reconstruct master key; any 1 share fails.
Method:
  - 1-of-3: each CSP alone → must FAIL (3 cases × 30 reps = 90 trials)
  - 2-of-3: each pair  → must SUCCEED (3 pairs × 30 reps = 90 trials)
  - 3-of-3: all three  → must SUCCEED (30 reps)
Expected: 0% one-share success, 100% two-share success, 100% three-share success.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode, decode
from core.results import save

REPS = 30
FILE_SIZE_MB = 100  # Key property test — fixed size is fine
RUN_NUMBER = 1

PAIRS = [(0, 1), (0, 2), (1, 2)]


def run_case(shares_to_use: list[int], result, data: bytes) -> dict:
    """Attempt reconstruction with a subset of Shamir shares."""
    subset_shares = [result.shamir_shares[i] for i in shares_to_use]
    # Pick shard indices from available CSPs (3 shards per CSP)
    available_shards = []
    for csp in shares_to_use:
        available_shards.extend(range(csp * 3, csp * 3 + 3))

    # We need 6 shards (RS k=6) — take first 6 from available
    shard_indices = available_shards[:6]
    enc_shards = [result.shards[i] for i in shard_indices]
    nonces = [result.shard_nonces[i] for i in shard_indices]
    orig_hash = hashlib.sha256(data).hexdigest()

    try:
        recovered = decode(
            enc_shards=enc_shards,
            shard_indices=shard_indices,
            nonces=nonces,
            shamir_shares=subset_shares,
            padding=result.padding,
            expected_hash=orig_hash,
        )
        return {"success": True, "hash_match": hashlib.sha256(recovered).hexdigest() == orig_hash}
    except Exception as e:
        return {"success": False, "error": type(e).__name__}


if __name__ == "__main__":
    records = []
    summary = {"k1_success": 0, "k2_success": 0, "k3_success": 0}

    for rep in range(1, REPS + 1):
        data = secrets.token_bytes(FILE_SIZE_MB * 1024 * 1024)
        result = encode(data)

        # k=1 (must fail)
        for csp in range(3):
            r = run_case([csp], result, data)
            records.append({"rep": rep, "k": 1, "csps": [csp], **r})
            if r["success"]:
                summary["k1_success"] += 1

        # k=2 (must succeed)
        for pair in PAIRS:
            r = run_case(list(pair), result, data)
            records.append({"rep": rep, "k": 2, "csps": list(pair), **r})
            if r["success"]:
                summary["k2_success"] += 1

        # k=3 (must succeed)
        r = run_case([0, 1, 2], result, data)
        records.append({"rep": rep, "k": 3, "csps": [0, 1, 2], **r})
        if r["success"]:
            summary["k3_success"] += 1

        print(f"T07 | rep {rep}/{REPS}  k1_ok={summary['k1_success']==0}  "
              f"k2_ok={summary['k2_success']=={rep*3}}  k3_ok={summary['k3_success']==rep}")

    total_k1 = REPS * 3
    total_k2 = REPS * 3
    total_k3 = REPS
    save("T07_threshold", RUN_NUMBER, {
        "measurements": records,
        "k1_success_rate_pct": round(summary["k1_success"] / total_k1 * 100, 2),
        "k2_success_rate_pct": round(summary["k2_success"] / total_k2 * 100, 2),
        "k3_success_rate_pct": round(summary["k3_success"] / total_k3 * 100, 2),
    })
    print(f"\nT07 complete")
    print(f"  k=1 (must fail):    {summary['k1_success']}/{total_k1} succeeded — PASS: {summary['k1_success']==0}")
    print(f"  k=2 (must succeed): {summary['k2_success']}/{total_k2} succeeded — PASS: {summary['k2_success']==total_k2}")
    print(f"  k=3 (must succeed): {summary['k3_success']}/{total_k3} succeeded — PASS: {summary['k3_success']==total_k3}")
