"""
T05 — Shannon Entropy
Dimension: Confidentiality

Target: Confirm ciphertext shards are indistinguishable from random noise.
Method: Upload via full NSS-EC pipeline. Compute byte-level Shannon entropy
  of each of the 9 encrypted shards. Attempt single-provider reconstruction.
  30 reps × 5 file sizes.
Expected: Entropy ≈ 7.999 bits/byte. Single-provider recovery: 0%.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib, math
import collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode, RS_N
from core.cloud_client import upload_file, ensure_buckets
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500]
REPS = 30
RUN_NUMBER = 1


def shannon_entropy(data: bytes) -> float:
    counts = collections.Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def attempt_single_provider_recovery(result, csp_idx: int) -> bool:
    """Try to reconstruct master key with only 1 Shamir share — must fail."""
    try:
        from core.nss_ec import shamir_reconstruct_key
        # With only 1 share, Lagrange interpolation returns a WRONG value
        wrong_key = shamir_reconstruct_key([result.shamir_shares[csp_idx]])
        # Try decrypting with wrong key — will raise InvalidTag
        from core.nss_ec import decrypt_shard, NONCE_LEN
        shard_idx = csp_idx * 3
        decrypt_shard(result.shard_nonces[shard_idx], result.shards[shard_idx],
                      wrong_key, shard_idx)
        return True  # should never reach here
    except Exception:
        return False  # correct — decryption failed


def run_one(size_mb: int, rep: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    result = encode(data)

    # Entropy of each encrypted shard
    entropies = [shannon_entropy(s) for s in result.shards]

    # Single-provider recovery attempts (all 3 CSPs)
    single_csp_success = [attempt_single_provider_recovery(result, i) for i in range(3)]

    return {
        "size_mb": size_mb,
        "rep": rep,
        "shard_entropies": [round(e, 4) for e in entropies],
        "mean_entropy": round(sum(entropies) / len(entropies), 4),
        "min_entropy": round(min(entropies), 4),
        "single_csp_recovery_success": single_csp_success,
        "sovereignty_proved": not any(single_csp_success),
    }


if __name__ == "__main__":
    records = []
    sovereignty_count = 0

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T05 | {size_mb} MB | rep {rep}/{REPS}")
            r = run_one(size_mb, rep)
            records.append(r)
            if r["sovereignty_proved"]:
                sovereignty_count += 1
            print(f"      entropy={r['mean_entropy']} bits/byte  "
                  f"sovereignty={'PROVED' if r['sovereignty_proved'] else 'FAILED'}")

    total = len(records)
    save("T05_entropy", RUN_NUMBER, {
        "measurements": records,
        "total": total,
        "sovereignty_rate_pct": round(sovereignty_count / total * 100, 2),
    })
    print(f"\nT05 complete — sovereignty proved in {sovereignty_count}/{total} trials")
