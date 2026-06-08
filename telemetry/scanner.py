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

Run: ``python3 telemetry/scanner.py [--probes N] [--timeout S]``
Requires: ``dnspython`` (``pip install -r requirements.txt``).
"""

from __future__ import annotations

import argparse
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


def main() -> None:
    ap = argparse.ArgumentParser(description="AlphaDNS resolver telemetry scanner")
    ap.add_argument("--probes", type=int, default=3, help="probes per (domain,resolver) [3]")
    ap.add_argument("--timeout", type=float, default=2.0, help="per-probe timeout seconds [2.0]")
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
    header = ["domain", "is_global_tld", "is_id_tld", "subdomain_depth", "hour", "timestamp"]
    for rid in ids:
        header += [f"{rid}_latency", f"{rid}_success"]
    header += ["optimal_class"]

    with open(OUTPUT_FILE, "a", newline="") as fh:
        writer = csv.writer(fh)
        if is_empty:
            writer.writerow(header)

        try:
            for n, domain in enumerate(domains, 1):
                is_global = int(domain.endswith((".com", ".net", ".org")))
                is_id = int(domain.endswith(".id"))
                depth = domain.count(".")  # MUST match the Go engine: len(labels)-1
                hour = datetime.now().hour

                results = {rid: measure(domain, ip, args.probes, args.timeout)
                           for rid, ip in resolvers.items()}

                # Informational best-effort label: fastest *reliable* resolver.
                ok = {rid: lat for rid, (s, lat) in results.items() if s and lat is not None}
                optimal = min(ok, key=ok.get) if ok else "1"  # fallback: anycast

                row = [domain, is_global, is_id, depth, hour, datetime.now().isoformat(timespec="seconds")]
                for rid in ids:
                    s, lat = results[rid]
                    row += ["" if lat is None else lat, int(s)]
                row += [optimal]
                writer.writerow(row)
                fh.flush()

                cells = " | ".join(
                    f"{rid}:{(str(results[rid][1])+'ms') if results[rid][0] else 'FAIL':>9}"
                    for rid in ids)
                win = resolvers.get(optimal, "?")
                print(f"[{n:4}/{len(domains)}] {domain:30} {cells}  -> {GREEN}{optimal} ({win}){RESET}")
        except KeyboardInterrupt:
            print(f"\n[!] Interrupted; partial data saved to {OUTPUT_FILE}")
            return

    print(f"[*] Scan complete -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
