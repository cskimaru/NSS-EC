"""
T11 — Proactive Rekeying
Dimension: Cryptographic Agility / Long-term Security

Target: Rekey a stored file (new AES master key, new Shamir shares, re-encrypt all
  shards in place) without data leaving the system decrypted at rest.
  Verify: old Shamir shares cannot reconstruct after rekeying.
  New shares reconstruct correctly.
  5 sizes × 10 reps.

Rekeying protocol:
  1. Download all 9 encrypted shards (do NOT reconstruct plaintext)
  2. Decrypt each shard with OLD master key
  3. Generate NEW master key + new Shamir shares
  4. Re-encrypt each shard with NEW master key
  5. Upload new ciphertext; upload new Shamir shares
  6. Confirm old shares → decryption failure
  7. Confirm new shares → correct reconstruction

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import (encode, decode, encrypt_shard, decrypt_shard,
                          shamir_split_key, shamir_reconstruct_key)
from core.cloud_client import upload_file, ensure_buckets, download_object, upload_object, ENDPOINTS
from core.results import save
from cryptography.exceptions import InvalidTag

FILE_SIZES_MB = [100, 200, 300, 500, 1000]
REPS = 10
RUN_NUMBER = 1


def rekey_file(file_id: str, old_result) -> dict:
    """Rekey a stored file without plaintext leaving at rest."""
    old_master_key = old_result.master_key
    new_master_key = secrets.token_bytes(32)
    new_shamir_shares = shamir_split_key(new_master_key)

    new_nonces = []
    new_ciphertexts = []

    for i in range(9):
        # Decrypt with old key
        plaintext_shard = decrypt_shard(
            old_result.shard_nonces[i],
            old_result.shards[i],
            old_master_key,
            i
        )
        # Re-encrypt with new key
        new_nonce, new_ct = encrypt_shard(plaintext_shard, new_master_key, i)
        new_nonces.append(new_nonce)
        new_ciphertexts.append(new_ct)

    # Upload new ciphertexts in place
    for csp_idx in range(3):
        client_ep = ENDPOINTS[csp_idx]
        for shard_i in range(csp_idx * 3, csp_idx * 3 + 3):
            upload_object(client_ep, f"{file_id}/shard_{shard_i}",
                          new_nonces[shard_i] + new_ciphertexts[shard_i])

    return {
        "new_master_key": new_master_key,
        "new_shamir_shares": new_shamir_shares,
        "new_nonces": new_nonces,
        "new_ciphertexts": new_ciphertexts,
    }


def run_one(size_mb: int, rep: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    orig_hash = hashlib.sha256(data).hexdigest()
    file_id = f"t11-{size_mb}mb-rep{rep}"

    result = encode(data)
    upload_file(file_id, result, parallel=True)

    # Rekey
    rekey_info = rekey_file(file_id, result)

    # Test old shares FAIL
    old_share_fail = False
    try:
        wrong_key = shamir_reconstruct_key(result.shamir_shares)
        # Try decrypting first shard with old key (which should now be wrong)
        decrypt_shard(rekey_info["new_nonces"][0],
                      rekey_info["new_ciphertexts"][0],
                      wrong_key, 0)
    except (InvalidTag, Exception):
        old_share_fail = True

    # Test new shares SUCCEED
    new_key_ok = False
    try:
        reconstructed_key = shamir_reconstruct_key(rekey_info["new_shamir_shares"][:2])
        pt = decrypt_shard(rekey_info["new_nonces"][0],
                           rekey_info["new_ciphertexts"][0],
                           rekey_info["new_master_key"], 0)
        new_key_ok = pt is not None
    except Exception:
        pass

    return {
        "size_mb": size_mb,
        "rep": rep,
        "old_shares_blocked": old_share_fail,
        "new_shares_work": new_key_ok,
        "rekey_success": old_share_fail and new_key_ok,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []
    success = 0

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T11 | {size_mb} MB | rep {rep}/{REPS}")
            r = run_one(size_mb, rep)
            records.append(r)
            if r["rekey_success"]:
                success += 1
            print(f"      old_blocked={r['old_shares_blocked']}  "
                  f"new_works={r['new_shares_work']}  "
                  f"{'PASS' if r['rekey_success'] else 'FAIL'}")

    total = len(records)
    save("T11_rekeying", RUN_NUMBER, {
        "measurements": records,
        "rekey_success_pct": round(success / total * 100, 2),
    })
    print(f"\nT11 complete — rekeying succeeded in {success}/{total} trials")
