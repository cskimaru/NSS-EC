# Research Gap: Secret Sharing + Distributed File Storage

**Project:** Cryptographically Sovereign Multi-Cloud Storage:
A Nested Secret Sharing and Erasure-Coded Architecture for Data Sovereignty
Without Sovereign Infrastructure

**Author:** Noah Kimaru | Kyoto Institute of Technology | 2026

---

## 1. The Gap

The combination of **Shamir Secret Sharing (SSS) with distributed object storage** is rare
in both academic literature and production systems. This document formally characterises
the gap and positions NSS-EC within it.

### 1.1 What Exists

**Shamir Secret Sharing** (Shamir, 1979) is well-studied as a theoretical primitive:
- Threshold schemes with proofs of information-theoretic security
- Verifiable SSS extensions (Feldman, 1987; Pedersen, 1991)
- Multi-party computation building blocks

**Distributed File Storage** is a mature field:
- Hadoop HDFS, Ceph, GlusterFS, MinIO, SeaweedFS (open-source)
- Amazon S3, Google Cloud Storage, Azure Blob (commercial)
- Erasure coding (Reed-Solomon) is standard for durability

**What is missing:** A production-grade architecture that **combines both** with a
cryptographic key placement rule ensuring no single provider can decrypt its own data.

### 1.2 Why SeaweedFS Has No Secret Sharing

SeaweedFS (the distributed object store used in this research) provides:
- Erasure coding for storage efficiency and durability
- Replication across volumes
- S3-compatible API

SeaweedFS does **not** provide:
- Shamir Secret Sharing of encryption keys
- Cross-provider key placement (the full-rotation rule)
- Cryptographic sovereignty: the guarantee that no single provider can read the data

This is not an oversight — SeaweedFS is designed as an infrastructure primitive, not an
end-to-end cryptographic system. The cryptographic layer must be built above it.

### 1.3 What NSS-EC Contributes

NSS-EC is the first system (to this author's knowledge) to implement:

1. **Nested secret sharing**: The master AES-256-GCM key is itself split (Shamir, k=2, n=3)
   and stored *across* providers, while each shard is encrypted with a *per-shard* key
   derived from the master key via HKDF-SHA256.

2. **Full-rotation key placement**: CSP i stores the AES keys for CSP (i+1)%3's shards.
   No CSP can decrypt the shards it stores — breaking the colocation assumption that
   makes single-provider subpoenas effective.

3. **RS(9,6) + SSS(2,3) layering**: Reed-Solomon provides storage efficiency (1.5×
   overhead) and k-of-9 shard recovery. Shamir provides cryptographic threshold control.
   The two thresholds are orthogonal: RS ensures *data availability*; Shamir ensures
   *key availability*. Both must be satisfied for reconstruction.

4. **Empirical characterisation of the RS/TCP interaction**: The ~487 ms RS encode stall
   at 100 MB exceeds Linux's TCP RTO_MIN (200 ms) floor, causing a cwnd reset at RTT ≥ 50 ms.
   This is the first quantitative mapping of this interaction in a secret-sharing context.

5. **Chunked upload as an RTO solution**: 4 MB chunks reduce per-chunk stall to ~19 ms,
   below RTO_MIN, eliminating the cliff. The crossover point (where chunking outperforms
   monolithic upload) is empirically identified at ~300–400 MB.

---

## 2. Literature Survey

### 2.1 Closest Prior Work

| Paper / System | SSS | Distributed Storage | Key Placement Rule | RS + SSS Layer |
|---|---|---|---|---|
| Shamir (1979) | ✓ | ✗ | ✗ | ✗ |
| PVSS schemes | Partial | ✗ | ✗ | ✗ |
| RAMP (Ogata et al.) | ✓ | ✗ | ✗ | ✗ |
| SecureCloud (academic) | ✓ | ✓ (simulated) | ✗ | ✗ |
| CAODASS (Kapusta et al.) | ✓ | ✓ | ✗ | Partial |
| NSS-EC (this work) | ✓ | ✓ (SeaweedFS) | **✓** | **✓** |

**CAODASS** (Kapusta, Memmi, Michalak, 2016) is the closest prior work. It proposes
combining secret sharing with cloud storage but does not implement or evaluate a
cross-provider key placement rule, and does not characterise RS/TCP interaction.

### 2.2 TCP RTO + Cryptographic Stall

No prior work was found that characterises the interaction between:
- Cryptographic processing stalls (RS encode, AES)
- TCP congestion control (cwnd reset at RTO_MIN)

This interaction is a novel empirical contribution of NSS-EC.

### 2.3 QUIC for Cryptographic Storage

The use of QUIC (RFC 9000) as a transport for secret-sharing-based storage systems is
not documented in prior literature. NSS-EC's `core/quic_transport.py` provides a
reference implementation for independent QUIC streams per shard, eliminating the
TCP RTO cliff by design (no cwnd window; independent stream flow control).

---

## 3. Novelty Claim

NSS-EC is novel in the intersection of:

1. Full-rotation key placement rule (cryptographic sovereignty without sovereign infrastructure)
2. Combined RS + SSS layering over real distributed object storage
3. Empirical characterisation of RS encode stall / TCP RTO interaction
4. Chunked upload as a principled solution with an identified crossover point
5. QUIC transport as an alternative path eliminating the TCP cliff

The research does not claim novelty in SSS alone, RS alone, or distributed storage alone.
The contribution is the architecture, the placement rule, and the empirical characterisation
of their performance properties.

---

## 4. Practical Significance

The architecture enables **data sovereignty without sovereign infrastructure**:

An organisation can store sensitive data in commercial multi-cloud environments (AWS, GCP,
Azure) such that:
- **No single CSP** can read the data (key placement rule)
- **Any two CSPs** together can reconstruct the master key (Shamir k=2)
- **Any six of nine shards** (from any two CSPs) reconstruct the plaintext (RS k=6)
- **Loss of any one CSP** is fully recoverable without key ceremony

This is relevant to:
- **GDPR / data residency compliance**: Data "resides" on no single provider's terms
- **Sovereign cloud alternatives**: Countries without national cloud infrastructure
  can achieve data sovereignty via placement rules over commercial CSPs
- **Cross-border data regulation**: Judicial subpoenas served to one CSP yield
  encrypted data with no held key

---

*Last updated: 2026-11-25*
