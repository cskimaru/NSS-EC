"""
NSS-EC Full Test Suite Runner
Cryptographically Sovereign Multi-Cloud Storage

Runs all T01–T16E in sequence. Each test saves results independently.
Use --only T06 to run a single test.
Use --skip T01,T02 to skip specific tests.

Author: Noah Kimaru | Kyoto Institute of Technology | 2026
"""

import sys
import os
import argparse
import subprocess
import time


TESTS = [
    ("T01", "tests/T01_parallel/run.py",           "Parallel vs Sequential Upload"),
    ("T02", "tests/T02_network/run.py",             "Network Conditions"),
    ("T03", "tests/T03_pipeline_overhead/run.py",   "Pipeline Overhead"),
    ("T04", "tests/T04_recovery/run.py",            "One-Cloud Offline Recovery"),
    ("T05", "tests/T05_entropy/run.py",             "Shannon Entropy / Sovereignty"),
    ("T06", "tests/T06_tamper/run.py",              "Tamper Detection"),
    ("T07", "tests/T07_threshold/run.py",           "Shamir Threshold Proof"),
    ("T08", "tests/T08_key_mismatch/run.py",        "Key–Data Mismatch (Full-Rotation Rule)"),
    ("T09", "tests/T09_provider_replacement/run.py","Provider Replacement"),
    ("T10", "tests/T10_erasure_coding/run.py",      "Erasure Coding Recovery (All Combos)"),
    ("T11", "tests/T11_rekeying/run.py",            "Proactive Rekeying"),
    ("T12", "tests/T12_storage_efficiency/run.py",  "Storage Efficiency"),
    ("T13", "tests/T13_cascading_failure/run.py",   "Cascading Failure (2-CSP Offline)"),
    ("T14", "tests/T14_throughput_diagnostic/run.py","Throughput Diagnostic"),
    ("T15", "tests/T15_memory/run.py",              "Memory Profiling"),
    ("T16A","tests/T16A_baseline/run.py",           "Unencrypted Baseline"),
    ("T16B","tests/T16B_rtt_sweep/run.py",          "RTT Sweep (2–250 ms)"),
    ("T16B2","tests/T16B2_dense_rtt/run.py",        "Dense RTT Sweep (40–60 ms)"),
    ("T16B3","tests/T16B3_straddle/run.py",         "Straddle Zone (49–51 ms)"),
    ("T16C","tests/T16C_batch_vs_stream/run.py",    "Batch vs Stream Upload"),
    ("T16D","tests/T16D_rto_fix/run.py",            "RTO Fix: BBR + BDP Tuning"),
    ("T16E","tests/T16E_chunked/run.py",            "Chunked Upload (RTO Solution)"),
]


def run_test(code: str, script: str, name: str) -> bool:
    print(f"\n{'='*70}")
    print(f"  {code}: {name}")
    print(f"{'='*70}")
    t0 = time.perf_counter()
    result = subprocess.run([sys.executable, script])
    elapsed = time.perf_counter() - t0
    ok = result.returncode == 0
    status = "PASS" if ok else "FAIL"
    print(f"\n  → {code} {status} in {elapsed:.1f}s")
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSS-EC Full Test Suite")
    parser.add_argument("--only", help="Run only this test code, e.g. T06")
    parser.add_argument("--skip", help="Comma-separated test codes to skip, e.g. T01,T02")
    args = parser.parse_args()

    skip_set = set(args.skip.split(",")) if args.skip else set()

    summary = []
    for code, script, name in TESTS:
        if args.only and code != args.only:
            continue
        if code in skip_set:
            print(f"  SKIP {code}")
            continue
        ok = run_test(code, script, name)
        summary.append((code, name, ok))

    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    for code, name, ok in summary:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status}  {code}  {name}")
    passed = sum(1 for _, _, ok in summary if ok)
    print(f"\n  {passed}/{len(summary)} tests passed")
