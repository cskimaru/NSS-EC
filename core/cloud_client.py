"""
NSS-EC Cloud Client — SeaweedFS S3-Compatible
Handles upload/download of shards and SSS shares across 3 simulated CSPs.

Full-rotation placement:
  CSP 0 → shards 0,1,2  + keys/shares for CSP 1's shards
  CSP 1 → shards 3,4,5  + keys/shares for CSP 2's shards
  CSP 2 → shards 6,7,8  + keys/shares for CSP 0's shards

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import io
import json
import time
import socket
import concurrent.futures
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from core.nss_ec import (
    RS_N, NUM_CSP, SHARDS_PER_CSP, key_owner,
    EncodeResult, encode, decode,
)

# ---------------------------------------------------------------------------
# SeaweedFS endpoints — same port layout as previous MinIO setup
# ---------------------------------------------------------------------------
ENDPOINTS = [
    {"name": "AWS-Japan",  "url": "http://133.16.241.50:8333", "bucket": "nss-aws"},
    {"name": "GCP-APAC",   "url": "http://133.16.241.50:8334", "bucket": "nss-gcp"},
    {"name": "Azure-US",   "url": "http://133.16.241.50:8335", "bucket": "nss-azure"},
]

ACCESS_KEY = "nssadmin"
SECRET_KEY = "nssadmin123"
REGION     = "us-east-1"

# TCP tuning — Big Fat Pipe / BDP-aware
_BOTO_CONFIG = Config(
    max_pool_connections=10,
    connect_timeout=10,
    read_timeout=120,
    retries={"max_attempts": 3, "mode": "adaptive"},
    tcp_keepalive=True,
)

# SO_SNDBUF / SO_RCVBUF set at socket level for BDP (128 MB)
_BDP_BUFFER = 128 * 1024 * 1024


def _make_client(endpoint: dict) -> boto3.client:
    return boto3.client(
        "s3",
        endpoint_url=endpoint["url"],
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION,
        config=_BOTO_CONFIG,
    )


def ensure_buckets():
    """Create buckets if they don't exist."""
    for ep in ENDPOINTS:
        client = _make_client(ep)
        try:
            client.head_bucket(Bucket=ep["bucket"])
        except ClientError:
            client.create_bucket(Bucket=ep["bucket"])
            print(f"  Created bucket {ep['bucket']} on {ep['name']}")


# ---------------------------------------------------------------------------
# Shard placement helpers
# ---------------------------------------------------------------------------
def shard_csp(shard_idx: int) -> int:
    """Return which CSP index owns (stores) shard_idx."""
    return shard_idx // SHARDS_PER_CSP


def upload_object(endpoint_or_client, key_or_bucket, data_or_key=None, data: bytes = None) -> float:
    """
    Flexible upload helper. Two calling conventions:
      upload_object(endpoint_dict, key, data)        ← convenience (T08, T09, T12, T16A)
      upload_object(boto3_client, bucket, key, data) ← low-level (internal)
    Returns upload time (s).
    """
    if isinstance(endpoint_or_client, dict):
        # Convenience: (endpoint, key, data)
        ep = endpoint_or_client
        client = _make_client(ep)
        bucket = ep["bucket"]
        key = key_or_bucket
        payload = data_or_key
    else:
        # Low-level: (client, bucket, key, data)
        client = endpoint_or_client
        bucket = key_or_bucket
        key = data_or_key
        payload = data
    t0 = time.perf_counter()
    client.put_object(Bucket=bucket, Key=key, Body=io.BytesIO(payload))
    return time.perf_counter() - t0


def download_object(endpoint_or_client, key_or_bucket: str, key: str = None) -> bytes:
    """
    Flexible download helper. Two calling conventions:
      download_object(endpoint_dict, key)             ← convenience
      download_object(boto3_client, bucket, key)      ← low-level
    """
    if isinstance(endpoint_or_client, dict):
        ep = endpoint_or_client
        client = _make_client(ep)
        bucket = ep["bucket"]
        obj_key = key_or_bucket
    else:
        client = endpoint_or_client
        bucket = key_or_bucket
        obj_key = key
    response = client.get_object(Bucket=bucket, Key=obj_key)
    return response["Body"].read()


# ---------------------------------------------------------------------------
# Full upload — parallel across CSPs
# ---------------------------------------------------------------------------
def upload_file(
    file_id: str,
    result: EncodeResult,
    parallel: bool = True,
) -> dict:
    """
    Upload all shards and SSS metadata for one encoded file.
    Returns timing dict.
    """
    clients = [_make_client(ep) for ep in ENDPOINTS]
    timings = {}

    def upload_csp(csp_idx: int):
        client = clients[csp_idx]
        bucket = ENDPOINTS[csp_idx]["bucket"]
        t_start = time.perf_counter()

        # Upload own shards
        for local_i in range(SHARDS_PER_CSP):
            shard_idx = csp_idx * SHARDS_PER_CSP + local_i
            payload = result.shard_nonces[shard_idx] + result.shards[shard_idx]
            upload_object(client, bucket, f"{file_id}/shard_{shard_idx}", payload)

        # Upload SSS share (this CSP's own share, stored here for recovery)
        x, y = result.shamir_shares[csp_idx]
        share_data = json.dumps({"x": x, "y": y, "padding": result.padding,
                                  "hash": result.file_hash}).encode()
        upload_object(client, bucket, f"{file_id}/share_{csp_idx}", share_data)

        # Upload AES keys for the NEXT CSP's shards (full rotation)
        next_csp = (csp_idx + 1) % NUM_CSP
        from core.nss_ec import derive_shard_key
        keys_payload = {}
        for local_i in range(SHARDS_PER_CSP):
            shard_idx = next_csp * SHARDS_PER_CSP + local_i
            key = derive_shard_key(result.master_key, shard_idx)
            keys_payload[str(shard_idx)] = key.hex()
        upload_object(client, bucket, f"{file_id}/keys_for_csp{next_csp}",
                      json.dumps(keys_payload).encode())

        return time.perf_counter() - t_start

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_CSP) as ex:
            futures = {ex.submit(upload_csp, i): i for i in range(NUM_CSP)}
            for f in concurrent.futures.as_completed(futures):
                i = futures[f]
                timings[f"csp{i}_upload_s"] = f.result()
    else:
        for i in range(NUM_CSP):
            timings[f"csp{i}_upload_s"] = upload_csp(i)

    return timings


# ---------------------------------------------------------------------------
# Full download — reconstruct from any 2 CSPs + any 6 shards
# ---------------------------------------------------------------------------
def download_file(
    file_id: str,
    available_csps: Optional[list[int]] = None,
) -> bytes:
    """
    Download and reconstruct file. If available_csps is None, uses all 3.
    Can reconstruct from any 2 CSPs (Shamir k=2) and any 6 shards (RS k=6).
    """
    if available_csps is None:
        available_csps = list(range(NUM_CSP))

    clients = [_make_client(ENDPOINTS[i]) for i in available_csps]

    # Collect SSS shares from available CSPs
    shamir_shares = []
    padding = None
    file_hash = None
    for idx, csp_i in enumerate(available_csps[:2]):
        raw = download_object(clients[idx], ENDPOINTS[csp_i]["bucket"],
                              f"{file_id}/share_{csp_i}")
        meta = json.loads(raw)
        shamir_shares.append((meta["x"], meta["y"]))
        if padding is None:
            padding = meta["padding"]
            file_hash = meta["hash"]

    # Collect shards (use first 6 available)
    enc_shards, shard_indices, nonces = [], [], []
    for idx, csp_i in enumerate(available_csps):
        client = clients[idx]
        bucket = ENDPOINTS[csp_i]["bucket"]
        for local_i in range(SHARDS_PER_CSP):
            shard_idx = csp_i * SHARDS_PER_CSP + local_i
            payload = download_object(client, bucket, f"{file_id}/shard_{shard_idx}")
            from core.nss_ec import NONCE_LEN
            nonces.append(payload[:NONCE_LEN])
            enc_shards.append(payload[NONCE_LEN:])
            shard_indices.append(shard_idx)
            if len(enc_shards) == 6:
                break
        if len(enc_shards) == 6:
            break

    return decode(enc_shards, shard_indices, nonces, shamir_shares, padding, file_hash)


# ---------------------------------------------------------------------------
# Chunked upload (T16E)
# ---------------------------------------------------------------------------
def upload_file_chunked(
    file_id: str,
    data: bytes,
    chunk_size_mb: float = 4.0,
    parallel: bool = True,
) -> dict:
    """Encode and upload in 4 MB chunks to keep per-chunk stall < RTO_MIN."""
    from core.nss_ec import encode_chunked
    chunks = encode_chunked(data, chunk_size_mb)
    all_timings = {"num_chunks": len(chunks), "chunks": []}
    for i, chunk_result in enumerate(chunks):
        t = upload_file(f"{file_id}/chunk_{i:04d}", chunk_result, parallel)
        all_timings["chunks"].append(t)
    return all_timings
