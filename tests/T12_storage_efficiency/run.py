"""
T12 — Storage Efficiency
Dimension: Resource Utilisation

Target: Measure actual per-CSP storage overhead vs. original file size.
  RS(9,6) theoretical: each shard = file_size/6; 9 shards = 1.5× total.
  Plus: 9 nonces (12 B each), 1 Shamir share per CSP (~80 B), 1 AES key (~40 B).
  Measure: bytes stored per CSP, total bytes stored across all CSPs, overhead ratio.

Method: 7 sizes × 10 reps. After upload, list objects and sum sizes.
Expected: overhead ≈ 1.5× + negligible metadata.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys, os, secrets
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.nss_ec import encode
from core.cloud_client import upload_file, ensure_buckets, _make_client, ENDPOINTS
from core.results import save

FILE_SIZES_MB = [100, 200, 300, 400, 500, 750, 1000]
REPS = 10
RUN_NUMBER = 1


def measure_stored_bytes(file_id: str) -> dict:
    """Sum all object sizes for this file_id across all 3 CSPs."""
    per_csp = []
    for csp_idx, ep in enumerate(ENDPOINTS):
        client = _make_client(ep)
        total = 0
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=ep["bucket"], Prefix=f"{file_id}/"):
            for obj in page.get("Contents", []):
                total += obj["Size"]
        per_csp.append(total)
    return {
        "per_csp_bytes": per_csp,
        "total_bytes": sum(per_csp),
        "max_csp_bytes": max(per_csp),
    }


def run_one(size_mb: int, rep: int) -> dict:
    original_bytes = size_mb * 1024 * 1024
    data = secrets.token_bytes(original_bytes)
    file_id = f"t12-{size_mb}mb-rep{rep}"

    result = encode(data)
    upload_file(file_id, result, parallel=True)

    stored = measure_stored_bytes(file_id)
    overhead_ratio = stored["total_bytes"] / original_bytes

    return {
        "size_mb": size_mb,
        "rep": rep,
        "original_bytes": original_bytes,
        **stored,
        "overhead_ratio": round(overhead_ratio, 4),
        "overhead_pct": round((overhead_ratio - 1) * 100, 2),
    }


if __name__ == "__main__":
    ensure_buckets()
    records = []

    for size_mb in FILE_SIZES_MB:
        for rep in range(1, REPS + 1):
            print(f"T12 | {size_mb} MB | rep {rep}/{REPS}")
            r = run_one(size_mb, rep)
            records.append(r)
            print(f"      original={r['original_bytes']//1024//1024}MB  "
                  f"total_stored={r['total_bytes']//1024//1024}MB  "
                  f"overhead={r['overhead_ratio']:.3f}×")

    save("T12_storage_efficiency", RUN_NUMBER, {
        "measurements": records,
        "mean_overhead_ratio": round(
            sum(r["overhead_ratio"] for r in records) / len(records), 4),
    })
    print(f"\nT12 complete — {len(records)} measurements saved")
