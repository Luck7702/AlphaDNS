import dns.resolver
import time
import csv
import pandas as pd
import os
import json

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
    resolver.timeout = 1.5
    try:
        start = time.perf_counter()
        resolver.resolve(domain, 'A') 
        end = time.perf_counter()
        return round((end - start) * 1000, 2)
    except Exception:
        return 999.0

if __name__ == "__main__":
    print("[*] Initiating network scan...")
    
    if os.path.exists(INPUT_FILE) and os.path.getsize(INPUT_FILE) > 0:
        target_path = INPUT_FILE
    else:
        target_path = PRESET_FILE

    df = pd.read_csv(target_path)
    domains = df.iloc[:, 0].dropna().astype(str).tolist()
    
    
    
    # Print Header with IPs once
    header_ips = [f"{RESOLVERS.get(k, '?.?.?.?'):>12}" for k in sorted(RESOLVERS.keys())]
    print(f"{'#':<5} {'Domain':<30} | {' | '.join(header_ips)} | Winner")
    print("-" * 100)

    with open(OUTPUT_FILE, mode='w', newline='') as csv_file:
        writer = csv.writer(csv_file)
        # Replaced 'Length' with 'Is_Global_TLD' to prevent ML overfitting
        writer.writerow(["Domain", "Is_Global_TLD", "Is_ID_TLD", "Subdomain_Depth", 
                         "C0", "C1", "C2", "C3", "Optimal_Class"])

        for i, domain in enumerate(domains, 1):
            domain = domain.replace("http://", "").replace("https://", "").replace("/", "").strip()
            
            # EXTRACT FEATURES
            is_global_tld = 1 if domain.endswith((".com", ".net", ".org")) else 0
            is_id_tld = 1 if domain.endswith(".id") else 0
            subdomain_depth = domain.count('.')
            
            # PING RESOLVERS
            latencies = {label: get_latency(domain, ip) for label, ip in RESOLVERS.items()}
            
            # --- FAILURE STATE LOGIC UPDATE ---
            # Filter out all resolvers that timed out (999.0)
            valid_latencies = {k: v for k, v in latencies.items() if v < 999.0}
            
            if not valid_latencies:
                # Total failure (Blocked/NXDOMAIN). Fallback to secure Cloudflare instead of ISP.
                optimal_class = "1"
            else:
                # Pick the fastest valid route
                optimal_class = min(valid_latencies, key=valid_latencies.get)
            
            writer.writerow([
                domain, is_global_tld, is_id_tld, subdomain_depth,
                latencies.get("0", 999.0), latencies.get("1", 999.0), 
                latencies.get("2", 999.0), latencies.get("3", 999.0),
                optimal_class
            ])
            
            # PRETTY PRINTING 
            lat_details = [f"{latencies.get(k, 999.0):10.1f}ms" for k in sorted(latencies.keys())]
            lat_str = " | ".join(lat_details)
            winner_ip = RESOLVERS.get(optimal_class, "Unknown")
            
            # Color coding for the winner (ANSI escape codes)
            GREEN = "\033[92m"
            RESET = "\033[0m"
            print(f"{i:03d}   {domain:<30} | {lat_str} | {GREEN}{winner_ip}{RESET}")

    print(f"\n[SUCCESS] Saved to: {OUTPUT_FILE}")