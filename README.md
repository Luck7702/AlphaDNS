# AlphaDNS: Intelligent Hybrid Local DNS Forwarder
**Research Prototype: Predictive DNS Selection for Balancing Resolution Success and Latency in Restricted Network Environments.**

> **⚠️ RESEARCH PROTOTYPE NOTICE**
> This repository contains a proof-of-concept prototype developed for academic research. It demonstrates the viability of utilizing Machine Learning for dynamic DNS routing. It is not currently intended for production-grade enterprise deployment. Features like continuous real-time model retraining are slated for future iterations.

---

## 📖 1. Project Overview
In standard networking configurations, DNS resolution relies on static heuristics (e.g., round-robin or strict priority lists). In restricted or highly congested environments (such as university or corporate networks), this static approach often results in "wait and fail" timeouts or data leakage of restricted domains to local ISP gateways.

**AlphaDNS** replaces static routing with a **Predictive Machine Learning Engine**. By extracting context-aware features from a DNS query, it dynamically predicts the optimal upstream resolver (ISP, Cloudflare, Google, or Quad9) to minimize latency while guaranteeing resolution success.

### Key Innovations
1. **Context-Aware Routing:** Replaces arbitrary heuristics with logical topological features (`Is_Global_TLD`, `Is_ID_TLD`, `Subdomain_Depth`). *Note: The current implementation uses the author's location (Indonesia, `.id`) as the primary local domain feature.*
2. **Zero-Leak Fallback:** Implements a fail-safe mechanism. If a domain is heavily restricted and fails all telemetry probes, the system defaults to a secure, encrypted resolver (Cloudflare, `1.1.1.1`) rather than defaulting to the local ISP in plain text.
3. **Decoupled Architecture:** Heavy mathematical training is isolated in an asynchronous Python pipeline, while real-time routing is handled by a high-speed, compiled Go engine executing raw decision-tree logic with near-zero overhead.

---

## 🏗️ 2. System Architecture & Directory Structure

The system is cleanly divided into three functional domains:

```text
AlphaDNS/
├── config.json                 # Global upstream resolver and network definitions
├── data/
│   ├── domains.csv             # Input corpus of domains for telemetry scanning
│   └── raw_probes.csv          # Telemetry output (Features + Resolution Labels)
├── engine/                     # REAL-TIME GO PROXY
│   ├── main.go                 # UDP Server and DNS message handler
│   ├── predictor.go            # Auto-generated Decision Tree logic (compiled)
│   ├── go.mod                  # Go module definitions
│   └── go.sum                  # Go dependency checksums
├── ml/                         # MACHINE LEARNING PIPELINE
│   ├── trainer.py              # Ingests telemetry, trains model, exports artifact
│   ├── export_model.py         # Translates .pkl artifact into Go source code
│   ├── artifact.pkl            # Serialized Scikit-Learn model
│   └── dns_decision_tree.png   # Visual graph of the current routing logic
└── telemetry/                  # DATA GATHERING
    └── scanner.py              # Probes resolvers, handles timeouts, applies fallback
```

## 📦 3. Prerequisites & Dependencies
### Python Environment
*   **Version:** Python 3.8+
*   **Dependencies:** `pandas`, `scikit-learn`, `dnspython`, `joblib`, `matplotlib`
*   **Install:** `pip install -r requirements.txt`

### Go Environment
*   **Version:** Go 1.18+
*   **Library:** `github.com/miekg/dns`

---

## 🚀 4. Operating Manual (How to Run)
Follow these steps in order to sync the ML model with the Proxy Engine:

### Step 1: Telemetry Collection
Run the scanner to probe your current network environment against the resolvers in `config.json`.
```bash
python3 telemetry/scanner.py
```

### Step 2: Model Training
Ingest the telemetry data to build the Decision Tree Classifier.
```bash
python3 ml/trainer.py
```

### Step 3: Engine Export
Translate the trained model into high-speed Go code (`predictor.go`).
```bash
python3 ml/export_model.py
```

### Step 4: Build & Deployment
Compile the Go engine and start the proxy server.
```bash
cd engine
go mod tidy
go build -o alphadns main.go predictor.go
./alphadns
```
> **Note:** The engine binds to UDP Port `5454` by default.

---

## 🧪 5. Verification & Testing
In a separate terminal, use `dig` to test the predictive routing:

*   **Test Global (.com):** `dig @127.0.0.1 -p 5454 google.com`
*   **Test Regional (.id):** `dig @127.0.0.1 -p 5454 unpad.ac.id`

Check the `./alphadns` terminal to view live classification logs.

---
**Author:** Dennis