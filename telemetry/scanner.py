import dns.resolver
import time
import csv
import pandas as pd
import os
import json
from datetime import datetime

# --- DYNAMIC PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "../data/domains.csv")
PRESET_FILE = os.path.join(BASE_DIR, "../data/domains_preset.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "../data/raw_probes.csv")
CONFIG_FILE = os.path.join(BASE_DIR, "../config.json")

# --- LOAD CONFIGURATION ---
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        RESOLVERS = config.get("resolvers", {})
except FileNotFoundError:
    print(f"[!] Warning: {CONFIG_FILE} not found. Ensure it exists in the root directory.")
    exit(1)
    
def get_latency(domain, server_ip):
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [server_ip]
    # Updated to 2.0s to align with our methodology of catching "long tail" timeouts
    resolver.timeout = 2.0 
    try:
        start = time.perf_counter()
        resolver.resolve(domain, 'A') 
        end = time.perf_counter()
        return round((end - start) * 1000, 2)
    except Exception:
        # Failure State modeled as a 2000ms p99 catastrophe (replaces 999.0)
        return 2000.0

if __name__ == "__main__":
    print(f"[*] Initiating network scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
    
    file_to_use = INPUT_FILE if os.path.exists(INPUT_FILE) else PRESET_FILE
    
    # Read domains
    domains = []
    with open(file_to_use, 'r') as f:
        reader = csv.reader(f)
        next(reader, None) # Skip header
        for row in reader:
            if row:
                domains.append(row[0])

    # --- PERMANENT AUTO-HEADER FIX ---
    file_exists = os.path.exists(OUTPUT_FILE)
    # Checks if the file is genuinely empty (0 bytes) even if it exists
    is_empty = os.stat(OUTPUT_FILE).st_size == 0 if file_exists else True

    # Always open in append mode to protect old data, but write header if it's "empty"
    with open(OUTPUT_FILE, 'a', newline='') as f:
        writer = csv.writer(f)

        if is_empty:
            writer.writerow([
                "domain", "is_global_tld", "is_id_tld", "subdomain_depth", "hour",
                "0_latency", "1_latency", "2_latency", "3_latency", "optimal_class"
            ])
    
        for domain in domains:
            is_global_tld = 1 if domain.endswith(('.com', '.net', '.org')) else 0
            is_id_tld = 1 if domain.endswith('.id') else 0
            subdomain_depth = domain.count('.')
            current_hour = datetime.now().hour
    
            # PING RESOLVERS
            latencies = {label: get_latency(domain, ip) for label, ip in RESOLVERS.items()}
    
            # --- FAILURE STATE LOGIC UPDATE ---
            # Filter out all resolvers that timed out (2000.0)
            valid_latencies = {k: v for k, v in latencies.items() if v < 2000.0}
    
            if not valid_latencies:
                # Total failure (Blocked/NXDOMAIN). Fallback to secure Cloudflare instead of ISP.
                optimal_class = "1"
            else:
                # Pick the fastest valid route 
                optimal_class = min(valid_latencies, key=valid_latencies.get)

            # Save the extended features to the CSV
            writer.writerow([
                domain, is_global_tld, is_id_tld, subdomain_depth, current_hour,
                latencies.get("0", 2000.0), latencies.get("1", 2000.0), 
                latencies.get("2", 2000.0), latencies.get("3", 2000.0),
                optimal_class
            ])
  
            # PRETTY PRINTING (Retained your original formatting!)
            lat_details = [f"{latencies.get(k, 2000.0):10.1f}ms" for k in sorted(latencies.keys())]
            lat_str = " | ".join(lat_details)
            winner_ip = RESOLVERS.get(optimal_class, "Unknown")
    
            # Color coding for the winner (ANSI escape codes)
            GREEN = "\033[92m"
            RESET = "\033[0m"
    
            print(f"[{domain:30}] {lat_str} | Best: {GREEN}{optimal_class} ({winner_ip}){RESET}")
    
    print(f"[*] Scan complete. Raw data exported to {OUTPUT_FILE}")
