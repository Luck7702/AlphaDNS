"""AlphaDNS telemetry scanner.

Probes every configured upstream resolver for every target domain and
records, per (domain, resolver):

  * ``success`` -- did the resolver return an A record (majority of probes)?
  * ``latency`` -- median latency in ms over the *successful* probes.

Design choices that matter for data quality
--------------------------------------------
* **Multiple probes + median.** A single probe over WiFi is dominated by
  jitter; the fastest-resolver argmin then flips on noise. We probe each
  pair ``--probes`` times (default 3) and keep the median of the
  successful probes, which materially de-noises the latency estimate.
* **Success is separate from latency.** Failures are recorded as
  ``success=0`` with a blank latency rather than a magic ``2000.0`` value,
  so downstream code never averages a sentinel into a real distribution.
  (``ml/dataset.py`` reads both schemas, old and new.)
* **Randomised domain order** each run, to avoid systematic ordering bias.
* **Concurrent probing** (``--workers N``, default 8) overlaps the per-pair
  network waits -- the big win when a resolver is timing out on every domain.
  Probes *within* a (domain, resolver) stay sequential so the median-of-3
  still samples independent moments; only different domains run in parallel,
  and the CSV is written only from the main thread. Note: high worker counts
  let simultaneous queries contend and can inflate measured latency, so for a
  rigorous latency claim use ``--workers 1``.

Run: ``python3 telemetry/scanner.py [--probes N] [--timeout S] [--workers N]``
Requires: ``dnspython`` (``pip install -r requirements.txt``).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime

import dns.resolver

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
INPUT_FILE = os.path.join(ROOT_DIR, "data", "domains.csv")
PRESET_FILE = os.path.join(ROOT_DIR, "data", "domains_preset.csv")
OUTPUT_FILE = os.path.join(ROOT_DIR, "data", "raw_probes.csv")
CONFIG_FILE = os.path.join(ROOT_DIR, "config.json")

GREEN, DIM, RESET = "\033[92m", "\033[2m", "\033[0m"


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit(f"[!] {CONFIG_FILE} not found. It must define a 'resolvers' map.")


def probe_once(domain: str, server_ip: str, timeout: float) -> float | None:
    """One probe. Returns latency in ms, or None on failure/timeout."""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [server_ip]
    resolver.lifetime = timeout
    resolver.timeout = timeout
    try:
        start = time.perf_counter()
        resolver.resolve(domain, "A")
        return round((time.perf_counter() - start) * 1000, 2)
    except Exception:
        return None


def measure(domain: str, server_ip: str, probes: int, timeout: float):
    """Probe ``probes`` times; return (success, median_latency_or_None)."""
    samples = [probe_once(domain, server_ip, timeout) for _ in range(probes)]
    ok = [s for s in samples if s is not None]
    # Majority vote on success; median latency over the successful probes.
    success = len(ok) > probes // 2
    latency = round(statistics.median(ok), 2) if ok else None
    return success, latency


def scan_domain(domain: str, resolvers: dict[str, str], ids: list[str],
                probes: int, timeout: float):
    """Probe every resolver for one domain. Returns (row, optimal_id, cells).

    Pure compute + network I/O and does no file writing, so it is safe to run
    in a worker thread (each ``probe_once`` builds its own resolver/socket).
    The shared CSV is written only from the main thread.
    """
    is_global = int(domain.endswith((".com", ".net", ".org")))
    is_id = int(domain.endswith(".id"))
    depth = domain.count(".")  # MUST match the Go engine: len(labels)-1
    hour = datetime.now().hour

    results = {rid: measure(domain, ip, probes, timeout)
               for rid, ip in resolvers.items()}

    # Informational best-effort label: fastest *reliable* resolver.
    ok = {rid: lat for rid, (s, lat) in results.items() if s and lat is not None}
    optimal = min(ok, key=ok.get) if ok else "1"  # fallback: anycast

    row = [domain, is_global, is_id, depth, hour,
           datetime.now().isoformat(timespec="seconds")]
    for rid in ids:
        s, lat = results[rid]
        row += ["" if lat is None else lat, int(s)]
    row += [optimal]

    cells = " | ".join(
        f"{rid}:{(str(results[rid][1])+'ms') if results[rid][0] else 'FAIL':>9}"
        for rid in ids)
    return row, optimal, cells


def probe_header(ids) -> list[str]:
    """The raw_probes.csv header for the given resolver ids.

    Defined once so the CLI and the GUI write byte-identical schemas.
    """
    header = ["domain", "is_global_tld", "is_id_tld", "subdomain_depth", "hour", "timestamp"]
    for rid in ids:
        header += [f"{rid}_latency", f"{rid}_success"]
    header += ["optimal_class"]
    return header


def run_scan(domains, resolvers, ids, *, probes, timeout, workers,
             on_result, should_stop=None):
    """Probe every domain across all resolvers, ``workers`` domains in parallel.

    This is the single concurrency engine shared by the CLI and the GUI: it
    owns only the thread pool and nothing about persistence/display. For each
    completed domain it calls ``on_result(done, total, row, optimal, cells)``
    on the consumer's thread -- the consumer decides whether to write the row,
    print it, or push it to a widget. ``should_stop`` (a zero-arg callable) is
    polled between completions for cooperative cancellation; pending probes are
    cancelled. Returns the number of domains actually completed.
    """
    total = len(domains)
    done = 0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = {executor.submit(scan_domain, d, resolvers, ids, probes, timeout): d
               for d in domains}
    try:
        # Completion order != submission order; rows are self-contained
        # (each carries its own timestamp) so order does not matter.
        for fut in concurrent.futures.as_completed(futures):
            if should_stop is not None and should_stop():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            row, optimal, cells = fut.result()
            done += 1
            on_result(done, total, row, optimal, cells)
        else:
            executor.shutdown(wait=True)
    except KeyboardInterrupt:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description="AlphaDNS resolver telemetry scanner")
    ap.add_argument("--probes", type=int, default=3, help="probes per (domain,resolver) [3]")
    ap.add_argument("--timeout", type=float, default=2.0, help="per-probe timeout seconds [2.0]")
    ap.add_argument("--workers", type=int, default=8,
                    help="domains probed in parallel [8]; use 1 for the most "
                         "faithful latency measurement")
    args = ap.parse_args()

    config = load_config()
    resolvers: dict[str, str] = config.get("resolvers", {})
    if not resolvers:
        sys.exit("[!] config.json has no 'resolvers' to probe.")
    ids = sorted(resolvers.keys(), key=int)

    source = INPUT_FILE if os.path.exists(INPUT_FILE) else PRESET_FILE
    with open(source) as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        domains = [row[0].strip() for row in reader if row and row[0].strip()]
    random.shuffle(domains)

    print(f"[*] Scan start {datetime.now():%Y-%m-%d %H:%M:%S} | "
          f"{len(domains)} domains x {len(ids)} resolvers x {args.probes} probes")

    is_empty = (not os.path.exists(OUTPUT_FILE)) or os.stat(OUTPUT_FILE).st_size == 0
    header = probe_header(ids)

    with open(OUTPUT_FILE, "a", newline="") as fh:
        writer = csv.writer(fh)
        if is_empty:
            writer.writerow(header)

        def on_result(done, total, row, optimal, cells):
            writer.writerow(row)
            fh.flush()
            win = resolvers.get(optimal, "?")
            print(f"[{done:4}/{total}] {row[0]:30} {cells}  -> {GREEN}{optimal} ({win}){RESET}")

        try:
            run_scan(domains, resolvers, ids,
                     probes=args.probes, timeout=args.timeout, workers=args.workers,
                     on_result=on_result)
        except KeyboardInterrupt:
            print(f"\n[!] Interrupted; cancelling pending probes, partial data saved to {OUTPUT_FILE}")
            return

    print(f"[*] Scan complete -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
