"""
================================================================================
  CASE 0: SHA-256 HASHING LATENCY — Pure Cryptographic Compute Benchmark
  THESIS: Quantitative Analysis and Optimization of Blockchain-Induced
          Latency in Real-Time Embedded Flight Control Systems

  Purpose:
    Isolate the cost of the SHA-256 hash operation itself — no serial port,
    no MAVLink, no network, no Geth — so it can be compared against the
    full PoA/PoS transaction latencies already measured. This tells you
    how much of the observed TX latency is "cryptographic compute" vs.
    "network / consensus overhead".

  Two measurements are taken:
    1. BATCHED THROUGHPUT (timeit) — the true average cost per hash. This
       amortizes Python's own timer-call overhead across a huge number of
       calls, which matters here because SHA-256 on a ~70-byte payload
       typically runs in the sub-microsecond to low-microsecond range —
       fast enough that calling time.perf_counter() around every single
       hash can itself distort the number.
    2. PER-CALL DISTRIBUTION (perf_counter per call) — gives you percentiles
       and jitter for a box/violin plot, at the cost of including some of
       that per-call Python/timer overhead in the numbers. Treat this as
       an upper bound, and the batched figure as the more trustworthy mean.
================================================================================
"""

import time
import timeit
import hashlib
import csv
import os
import statistics
from datetime import datetime

# ============================================================
#  CONFIGURATION — edit only this section if needed
# ============================================================
LOG_DIR    = "/home/merajpi/Nabil/logs"
ITERATIONS = 100_000       # individual timed hashes -> distribution/percentiles
BATCH_SIZE = 1_000_000     # hashes in the timeit batch -> true average cost

# Same payload shape/size as the telemetry data your PoA/PoS scripts hash
# and embed in a transaction, so the compute cost is directly comparable.
PAYLOAD = (
    "ALT:123.45,SPD:12.34,LAT:23.7809981,LON:90.4152540,HDG:275,SAT:11"
).encode()


# ============================================================
#  MEASUREMENTS
# ============================================================
def batched_throughput(payload: bytes, n: int) -> float:
    """True average cost per hash, in microseconds, using timeit to
    amortize per-call timer overhead across n calls."""
    t = timeit.timeit(lambda: hashlib.sha256(payload).digest(), number=n)
    return (t / n) * 1e6


def per_call_distribution(payload: bytes, n: int) -> list:
    """Per-call latencies (microseconds) for percentile/jitter analysis.
    Includes Python interpreter + perf_counter() call overhead."""
    samples = [0.0] * n
    for i in range(n):
        t0 = time.perf_counter()
        hashlib.sha256(payload).digest()
        t1 = time.perf_counter()
        samples[i] = (t1 - t0) * 1e6
    return samples


# ============================================================
#  MAIN
# ============================================================
def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp_str = datetime.now().strftime("%H%M-%d%m%Y")
    log_filename = os.path.join(LOG_DIR, f"case0_sha256_{timestamp_str}.csv")

    print("=" * 70)
    print("  CASE 0: SHA-256 HASHING LATENCY (pure compute, no network)")
    print("=" * 70)
    print(f"Payload : {PAYLOAD!r}")
    print(f"Size    : {len(PAYLOAD)} bytes\n")

    # Warm up (interpreter/CPU cache warmup — discard these)
    for _ in range(1000):
        hashlib.sha256(PAYLOAD).digest()

    print(f"[1/2] Batched throughput over {BATCH_SIZE:,} hashes...")
    avg_us = batched_throughput(PAYLOAD, BATCH_SIZE)
    print(f"      -> {avg_us:.4f} us/hash   (~{1e6 / avg_us:,.0f} hashes/sec)")

    print(f"\n[2/2] Per-call distribution over {ITERATIONS:,} hashes...")
    samples = per_call_distribution(PAYLOAD, ITERATIONS)

    mean_v   = statistics.mean(samples)
    median_v = statistics.median(samples)
    std_v    = statistics.stdev(samples)
    sorted_s = sorted(samples)
    p95      = sorted_s[int(0.95 * len(sorted_s))]
    p99      = sorted_s[int(0.99 * len(sorted_s))]
    min_v, max_v = sorted_s[0], sorted_s[-1]

    print(f"      mean   : {mean_v:.4f} us")
    print(f"      median : {median_v:.4f} us")
    print(f"      std    : {std_v:.4f} us")
    print(f"      p95    : {p95:.4f} us")
    print(f"      p99    : {p99:.4f} us")
    print(f"      min/max: {min_v:.4f} / {max_v:.4f} us")

    # Save raw per-call samples for downstream comparative plotting
    with open(log_filename, mode="w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Iteration", "SHA256_Latency_us"])
        for i, s in enumerate(samples):
            w.writerow([i, f"{s:.6f}"])

    print(f"\n[INFO] Per-call samples saved -> {log_filename}")

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Batched true average (recommended)     : {avg_us:.4f} us  "
          f"(~{avg_us / 1000:.6f} ms)")
    print(f"  Per-call mean (incl. timer overhead)   : {mean_v:.4f} us")
    print(f"  Per-call p99 (tail / jitter)           : {p99:.4f} us")
    print("=" * 70)
    print("\nFor context: your measured full-transaction latencies were")
    print("  PoA (submission only)  ~12 ms      ~12,000 us")
    print("  PoS (confirmed T_total)~6,063 ms   ~6,063,000 us")
    print("SHA-256 compute is expected to be several orders of magnitude")
    print("smaller than both — i.e. the observed TX latency is dominated")
    print("by network/RPC/consensus, not by the hashing operation itself.")


if __name__ == "__main__":
    main()
