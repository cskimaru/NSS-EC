# Cryptographically Sovereign Multi-Cloud Storage
## A Nested Secret Sharing and Erasure-Coded Architecture for Data Sovereignty Without Sovereign Infrastructure

**Author:** Noah Kimaru  
**Institution:** Kyoto Institute of Technology  
**Supervisor:** Masuda Hideo  
**Updated:** 2026-11-25

---

## Research Objective

Enforce cryptographic key-data separation and master-key availability across multiple cloud providers through one architectural mechanism — without replicating full ciphertext data and without trusting any single provider.

## Architecture (NSS-EC)

Three production-grade cryptographic layers composed in sequence:

```
File
 │
 ├─► Reed-Solomon (zfec k=6, m=3, n=9)  → 9 shards (any 6 reconstruct)
 │
 ├─► AES-256-GCM per shard              → authenticated ciphertext
 │   (key = HKDF-SHA256(master_key, shard_index))
 │
 └─► Shamir SSS (k=2, n=3)             → 3 shares of master key
     stored CROSS-CLOUD (full rotation)

Provider 0 (AWS/Japan)   → shards [0,1,2]  + keys for GCP + SSS share S1
Provider 1 (GCP/APAC)    → shards [3,4,5]  + keys for Azure + SSS share S2
Provider 2 (Azure/US)    → shards [6,7,8]  + keys for AWS + SSS share S3
```

No provider holds the decryption key for its own shards. Any 2 of 3 providers reconstruct the master key. Any 6 of 9 shards reconstruct the file.

## Infrastructure (SeaweedFS — Production Equivalent)

| Simulated CSP | SeaweedFS Port | Network Profile |
|---------------|---------------|-----------------|
| AWS / Japan | 8333 | 2 ms RTT / 0.5 ms jitter / 1 Gbps |
| GCP / APAC | 8334 | 80 ms RTT / 5 ms jitter / 100 Mbps |
| Azure / US | 8335 | 180 ms RTT / 10 ms jitter / 50 Mbps |

SeaweedFS exposes an S3-compatible API identical to the previous MinIO setup. All boto3 client code is unchanged. Results from this environment are **not directly comparable** to the MinIO results — all tests T01–T16 are run fresh on this infrastructure.

## Experiment Series

| Test | Name | Dimension |
|------|------|-----------|
| T01 | Throughput: Parallel vs Sequential Transfer | Performance |
| T02 | Network Conditions | Availability |
| T03 | Pipeline Overhead | Performance |
| T04 | One-Cloud Offline Recovery | Availability |
| T05 | Shannon Entropy | Confidentiality |
| T06 | Tamper Detection | Integrity |
| T07 | Threshold Proof | Availability |
| T08 | Key-Data Mismatch | Confidentiality |
| T09 | Provider Replacement Without Exposure | Sovereignty |
| T10 | Erasure Coding on Real CSP Profiles | Availability |
| T11 | Proactive Re-keying | Security |
| T12 | Storage Efficiency | Efficiency |
| T13 | Sequential Cascading Failure | Resilience |
| T14 | Throughput Diagnostic — 4 Stages | Diagnostic |
| T15 | Per-Stage Memory & Time Profiling | Diagnostic |
| T16A | Unencrypted Baseline | Optimisation |
| T16B | Broad RTT Sweep 2–250 ms | Optimisation |
| T16B2 | Dense RTT Sweep 40–60 ms | Optimisation |
| T16B3 | Straddle Zone 49–51 ms | Optimisation |
| T16C | Batch vs Stream Pipeline | Optimisation |
| T16D | Kernel RTO_MIN Fix Attempt | Optimisation |
| T16E | Chunked Upload — 4 MB Chunks | Optimisation |

## Quick Start

```bash
# 1. Start infrastructure
cd infra && docker compose up -d
cd infra && bash tc_netem.sh apply

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run any test
python tests/T01_parallel/run.py
```

## Results

All results saved to `results/<test_id>/run_<n>.json`. Each file contains raw measurements, computed statistics, and environment metadata. Never modify result files — append only.

## Transport Options

- **Default:** boto3 S3-compatible (TCP, BDP-tuned buffers, BBR congestion control)
- **QUIC:** `--transport quic` (aioquic-based, eliminates TCP RTO cliff)
- **Enhanced TCP:** `--transport tcp-enhanced` (BBR + 128 MB buffers + SO_SNDBUF tuning)
