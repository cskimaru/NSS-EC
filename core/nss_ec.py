"""
NSS-EC Core Pipeline — Production Grade
Cryptographically Sovereign Multi-Cloud Storage

Layers (in order):
  1. Reed-Solomon erasure coding  — zfec k=6, m=3, n=9
  2. AES-256-GCM authenticated encryption per shard
  3. Shamir Secret Sharing (k=2, n=3) over GF(2^521-1)
  4. Full-rotation key-data separation (no provider decrypts its own shards)

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import os
import struct
import hashlib
import secrets
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Optional

import zfec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RS_K        = 6          # data shards (minimum needed to reconstruct)
RS_M        = 3          # parity shards
RS_N        = RS_K + RS_M  # total shards = 9
NUM_CSP     = 3          # number of cloud providers
SHARDS_PER_CSP = RS_N // NUM_CSP  # 3 shards per CSP

SHAMIR_K    = 2          # minimum shares to reconstruct master key
SHAMIR_N    = 3          # total shares (one per CSP)
SHAMIR_PRIME = (1 << 521) - 1  # Mersenne prime M521

AES_KEY_LEN = 32         # AES-256
NONCE_LEN   = 12         # AES-GCM standard nonce
TAG_LEN     = 16         # AES-GCM authentication tag

# Full-rotation key placement:
# CSP i stores shards [i*3 .. i*3+2] and holds keys for CSP (i+1) % 3
# i.e. CSP 0 (AWS)   → shards 0,1,2 + keys for shards 3,4,5 (GCP's shards)
# CSP 1 (GCP)  → shards 3,4,5 + keys for shards 6,7,8 (Azure's shards)
# CSP 2 (Azure)→ shards 6,7,8 + keys for shards 0,1,2 (AWS's shards)
def key_owner(shard_idx: int) -> int:
    """Return which CSP index holds the AES key for shard_idx."""
    return (shard_idx // SHARDS_PER_CSP - 1) % NUM_CSP


# ---------------------------------------------------------------------------
# Shamir Secret Sharing over GF(2^521-1)
# ---------------------------------------------------------------------------
def _shamir_split(secret_int: int, k: int, n: int, prime: int) -> list[tuple[int,int]]:
    """Split secret_int into n shares, any k reconstruct."""
    coeffs = [secret_int] + [secrets.randbelow(prime) for _ in range(k - 1)]
    shares = []
    for x in range(1, n + 1):
        y = sum(c * pow(x, i, prime) for i, c in enumerate(coeffs)) % prime
        shares.append((x, y))
    return shares

def _shamir_reconstruct(shares: list[tuple[int,int]], prime: int) -> int:
    """Lagrange interpolation to reconstruct secret."""
    secret = 0
    for i, (xi, yi) in enumerate(shares):
        num = den = 1
        for j, (xj, _) in enumerate(shares):
            if i != j:
                num = (num * (-xj)) % prime
                den = (den * (xi - xj)) % prime
        secret = (secret + yi * num * pow(den, prime - 2, prime)) % prime
    return secret

def shamir_split_key(master_key: bytes) -> list[tuple[int,int]]:
    secret_int = int.from_bytes(master_key, 'big')
    return _shamir_split(secret_int, SHAMIR_K, SHAMIR_N, SHAMIR_PRIME)

def shamir_reconstruct_key(shares: list[tuple[int,int]]) -> bytes:
    secret_int = _shamir_reconstruct(shares, SHAMIR_PRIME)
    return secret_int.to_bytes(AES_KEY_LEN, 'big')


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------
def derive_shard_key(master_key: bytes, shard_index: int) -> bytes:
    """Derive a unique AES-256 key for each shard using HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=AES_KEY_LEN,
        salt=None,
        info=f"nss-ec-shard-{shard_index}".encode(),
        backend=default_backend()
    )
    return hkdf.derive(master_key)


# ---------------------------------------------------------------------------
# Encode / Decode
# ---------------------------------------------------------------------------
def _pad(data: bytes) -> tuple[bytes, int]:
    """Pad data so length is divisible by RS_K."""
    rem = len(data) % RS_K
    pad = (RS_K - rem) % RS_K
    return data + b'\x00' * pad, pad

def rs_encode(data: bytes) -> tuple[list[bytes], int]:
    """Reed-Solomon encode data into RS_N shards. Returns (shards, padding)."""
    padded, padding = _pad(data)
    chunk = len(padded) // RS_K
    enc = zfec.Encoder(RS_K, RS_N)
    shards = enc.encode([padded[i*chunk:(i+1)*chunk] for i in range(RS_K)])
    return shards, padding

def rs_decode(shards: list[bytes], indices: list[int], padding: int) -> bytes:
    """Reed-Solomon decode from any RS_K shards."""
    dec = zfec.Decoder(RS_K, RS_N)
    blocks = dec.decode(shards, indices)
    data = b''.join(blocks)
    return data[:-padding] if padding else data


# ---------------------------------------------------------------------------
# Encrypt / Decrypt shards
# ---------------------------------------------------------------------------
def encrypt_shard(shard: bytes, master_key: bytes, shard_index: int) -> tuple[bytes, bytes]:
    """AES-256-GCM encrypt a shard. Returns (nonce, ciphertext_with_tag)."""
    key = derive_shard_key(master_key, shard_index)
    nonce = os.urandom(NONCE_LEN)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, shard, None)
    return nonce, ciphertext

def decrypt_shard(nonce: bytes, ciphertext: bytes, master_key: bytes, shard_index: int) -> bytes:
    """AES-256-GCM decrypt. Raises InvalidTag on tampering."""
    key = derive_shard_key(master_key, shard_index)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# High-level pipeline
# ---------------------------------------------------------------------------
@dataclass
class EncodeResult:
    """Everything needed to upload and later reconstruct a file."""
    master_key:    bytes
    shamir_shares: list[tuple[int,int]]   # [(x, y), ...] one per CSP
    shard_nonces:  list[bytes]            # one per shard
    shards:        list[bytes]            # encrypted shards
    padding:       int
    file_hash:     str                    # SHA-256 of original plaintext
    timings:       dict = field(default_factory=dict)
    memory_peak_mb: float = 0.0


def encode(data: bytes, profile: bool = False) -> EncodeResult:
    """
    Full NSS-EC encode pipeline.
    Returns EncodeResult with everything needed to upload.
    """
    timings = {}
    tracemalloc.start() if profile else None

    t0 = time.perf_counter()
    file_hash = hashlib.sha256(data).hexdigest()

    # 1. Generate master key
    master_key = secrets.token_bytes(AES_KEY_LEN)

    # 2. Reed-Solomon encode
    t1 = time.perf_counter()
    raw_shards, padding = rs_encode(data)
    timings['rs_encode_ms'] = (time.perf_counter() - t1) * 1000

    # 3. AES-256-GCM encrypt each shard
    t2 = time.perf_counter()
    nonces, enc_shards = [], []
    for i, shard in enumerate(raw_shards):
        nonce, ct = encrypt_shard(shard, master_key, i)
        nonces.append(nonce)
        enc_shards.append(ct)
    timings['aes_encrypt_ms'] = (time.perf_counter() - t2) * 1000

    # 4. Shamir split master key
    t3 = time.perf_counter()
    shares = shamir_split_key(master_key)
    timings['shamir_split_ms'] = (time.perf_counter() - t3) * 1000

    timings['total_encode_ms'] = (time.perf_counter() - t0) * 1000

    mem_peak = 0.0
    if profile:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        mem_peak = peak / 1024 / 1024

    return EncodeResult(
        master_key=master_key,
        shamir_shares=shares,
        shard_nonces=nonces,
        shards=enc_shards,
        padding=padding,
        file_hash=file_hash,
        timings=timings,
        memory_peak_mb=mem_peak,
    )


def decode(
    enc_shards: list[bytes],
    shard_indices: list[int],
    nonces: list[bytes],
    shamir_shares: list[tuple[int,int]],
    padding: int,
    expected_hash: Optional[str] = None,
) -> bytes:
    """
    Full NSS-EC decode pipeline.
    shamir_shares: at least SHAMIR_K shares.
    enc_shards / shard_indices / nonces: at least RS_K encrypted shards.
    """
    # 1. Reconstruct master key
    master_key = shamir_reconstruct_key(shamir_shares[:SHAMIR_K])

    # 2. Decrypt shards
    raw_shards = [
        decrypt_shard(nonces[i], enc_shards[i], master_key, shard_indices[i])
        for i in range(len(enc_shards))
    ]

    # 3. Reed-Solomon decode
    data = rs_decode(raw_shards, shard_indices, padding)

    # 4. Verify integrity
    if expected_hash:
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_hash:
            raise ValueError(f"Hash mismatch: expected {expected_hash}, got {actual}")

    return data


# ---------------------------------------------------------------------------
# Chunked encode (T16E solution)
# ---------------------------------------------------------------------------
def encode_chunked(data: bytes, chunk_size_mb: float = 4.0) -> list[EncodeResult]:
    """
    Split data into chunks and encode each independently.
    Per-chunk RS stall ≈ chunk_size / full_file_size × full_stall
    For 4 MB chunks: ~19 ms ≪ TCP_RTO_MIN (200 ms)
    """
    chunk_bytes = int(chunk_size_mb * 1024 * 1024)
    chunks = [data[i:i+chunk_bytes] for i in range(0, len(data), chunk_bytes)]
    return [encode(chunk) for chunk in chunks]
