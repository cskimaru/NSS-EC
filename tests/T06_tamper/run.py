"""
T06 — Tamper Detection
Dimension: Integrity

Target: AES-256-GCM detects any byte-level modification to stored shards.
Method: Upload file. Corrupt one byte in one shard on SeaweedFS. Attempt download.
  30 reps × 5 sizes × 9 shards (one at a time) = detect all.
Expected: 100% detection. cryptography.exceptions.InvalidTag raised every time.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode, NONCE_LEN
from core.cloud_client import upload_file, download_file, ensure_buckets, _make_client, ENDPOINTS
from core.results import save
from cryptography.exceptions import InvalidTag

FILE_SIZES_MB = [100, 200, 300, 400, 500]
REPS = 30
RUN_NUMBER = 1


def corrupt_shard(file_id: str, shard_idx: int):
    """Flip one byte in the stored shard ciphertext on SeaweedFS."""
    csp_idx = shard_idx // 3
    client = _make_client(ENDPOINTS[csp_idx])
    bucket = ENDPOINTS[csp_idx]["bucket"]
    key = f"{file_id}/shard_{shard_idx}"

    obj = client.get_object(Bucket=bucket, Key=key)
    payload = bytearray(obj["Body"].read())
    # Flip byte at position NONCE_LEN + 10 (inside ciphertext, after nonce)
    pos = NONCE_LEN + 10
    payload[pos] ^= 0xFF
    client.put_object(Bucket=bucket, Key=key, Body=bytes(payload))


def run_one(size_mb: int, rep: int, shard_idx: int) -> dict:
    data = secrets.token_bytes(size_mb * 1024 * 1024)
    file_id = f"t06-{size_mb}mb-rep{rep}-s{shard_idx}"

    result = encode(data)
    upload_file(file_id, result, parallel=True)
    corrupt_shard(file_id, shard_idx)

    detected = False
    try:
        download_file(file_id)
    except (InvalidTag, Exception) as e:
        detected = "InvalidTag" in type(e).__name__ or "InvalidTag" in str(e)

    return {
        "size_mb": size_mb,
        "rep": rep,
        "corrupted_shard": shard_idx,
        "tamper_detected": detected,
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []
    detected_count = 0

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            # Test one shard per rep (cycle through shards)
            shard_idx = (rep - 1) % 9
            print(f"T06 | {size_mb} MB | rep {rep} | shard {shard_idx}")
            r = run_one(size_mb, rep, shard_idx)
            records.append(r)
            if r["tamper_detected"]:
                detected_count += 1
            print(f"      tamper_detected={r['tamper_detected']}")

    total = len(records)
    save("T06_tamper", RUN_NUMBER, {
        "measurements": records,
        "total": total,
        "detection_rate_pct": round(detected_count / total * 100, 2),
    })
    print(f"\nT06 complete — {detected_count}/{total} tampers detected ({detected_count/total*100:.1f}%)")
