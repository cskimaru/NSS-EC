"""
T10 — Erasure Coding Recovery
Dimension: Availability

Target: Confirm RS(9,6) recovery: any 6-of-9 shards reconstruct original data.
  Enumerate all C(9,6)=84 shard combinations. Each must succeed.
  Also confirm: any 5-of-9 (below threshold) fails to reconstruct.
  10 sizes × 10 reps.

Expected: 84/84 six-shard combos succeed; 5-shard combos fail.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib
import itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode, rs_decode, decrypt_shard, RS_K, RS_N, derive_shard_key
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
REPS = 10
RUN_NUMBER = 1


def try_rs_recover(result, shard_indices: list[int], data: bytes) -> bool:
    """Attempt RS decode from exactly the given shard indices."""
    shards_subset = [result.shards[i] for i in shard_indices]
    # Decrypt each shard first
    plaintext_shards = []
    for idx, raw in zip(shard_indices, shards_subset):
        try:
            pt = decrypt_shard(result.shard_nonces[idx], raw, result.master_key, idx)
            plaintext_shards.append(pt)
        except Exception:
            return False

    try:
        recovered = rs_decode(plaintext_shards, shard_indices, result.padding)
        return hashlib.sha256(recovered).hexdigest() == hashlib.sha256(data).hexdigest()
    except Exception:
        return False


def run_one(size_mb: int, rep: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    result = encode(data)

    # Test all C(9,6)=84 combinations of 6 shards
    all_combos_6 = list(itertools.combinations(range(RS_N), RS_K))
    success_6 = sum(try_rs_recover(result, list(c), data) for c in all_combos_6)

    # Test 10 random 5-shard combos (should all fail)
    all_combos_5 = list(itertools.combinations(range(RS_N), RS_K - 1))
    import random
    sample_5 = random.sample(all_combos_5, min(10, len(all_combos_5)))
    failures_5 = sum(1 for c in sample_5 if not try_rs_recover(result, list(c), data))

    return {
        "size_mb": size_mb,
        "rep": rep,
        "k6_success": success_6,
        "k6_total": len(all_combos_6),
        "k5_failures": failures_5,
        "k5_sampled": len(sample_5),
        "rs_threshold_proven": success_6 == len(all_combos_6) and failures_5 == len(sample_5),
    }


if __name__ == "__main__":
    records = []
    proven = 0

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T10 | {size_mb} MB | rep {rep}/{REPS}")
            r = run_one(size_mb, rep)
            records.append(r)
            if r["rs_threshold_proven"]:
                proven += 1
            print(f"      6-shard={r['k6_success']}/84  5-shard-fail={r['k5_failures']}/{r['k5_sampled']}  "
                  f"{'PASS' if r['rs_threshold_proven'] else 'FAIL'}")

    total = len(records)
    save("T10_erasure_coding", RUN_NUMBER, {
        "measurements": records,
        "threshold_proven_pct": round(proven / total * 100, 2),
    })
    print(f"\nT10 complete — RS(9,6) threshold proven in {proven}/{total} trials")
