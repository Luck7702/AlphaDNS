# AlphaDNS 🚀
**An ML-Driven Hybrid DNS Forwarder — and an honest evaluation of whether it helps.**

> **Research question:** *Can a machine-learning–based hybrid DNS resolver
> selection mechanism improve web latency and resolution success in Indonesia,
> versus a static single-resolver configuration?*

AlphaDNS is a research prototype **and the measurement harness that tests its own
hypothesis**. It does not assume ML routing wins — it measures it, and reports
the result whether positive or negative.

---

## TL;DR — what the current data shows

On the bundled dataset (520 Indonesia-relevant domains, probed 21:00–22:00 over
WiFi), **per-query ML resolver selection does _not_ beat a single reliable
anycast resolver.** The evaluation harness (`analysis/evaluate.py`) produces:

| policy | success % | mean eff. latency (ms) | p95 (ms) | regret vs oracle (ms) |
|---|---:|---:|---:|---:|
| static ISP (`103.88.88.88`) | 73.3 | 658.9 | 2000 | 507.8 |
| static Cloudflare (`1.1.1.1`) | 95.5 | 214.6 | 816 | 63.4 |
| **static Google (`8.8.8.8`)** | **95.5** | **198.6** | **806** | **47.5** |
| static Quad9 (`9.9.9.9`) | 80.8 | 576.9 | 2000 | 425.8 |
| random | 86.1 | 421.4 | 2000 | 270.2 |
| **ML hybrid** (out-of-fold) | 95.5 | 198.6 | 806 | 47.5 |
| oracle (upper bound) | 95.7 | 151.1 | 307 | 0 |

**Mechanism behind the result:**
1. **Resolution success dominates, not speed.** The local ISP resolver fails
   **27%** of queries and Quad9 **19%**, while Cloudflare/Google fail ~4.5% and
   already match the oracle's 95.7% success ceiling.
2. **Latency among reliable resolvers is noise.** The fastest resolver flips on
   **62%** of repeat probes of the same domain — there is no stable, learnable
   "which is fastest" signal from static features.
3. So the model correctly **collapses to "always pick a reliable anycast
   resolver."** Its out-of-fold numbers are statistically indistinguishable from
   the best static baseline (95% CI on the delta crosses zero).

This is a **credible negative result**, not a failure of the code. See
[CLAUDE.md](CLAUDE.md) for the full reasoning and what *would* make ML pay off.

---

## 🏗️ Architecture

Two decoupled halves:

1. **Telemetry & analysis (Python)** — probes resolvers, trains the model, and
   (crucially) **evaluates** ML routing against static / random / oracle
   policies on held-out data.
2. **Real-time engine (Go)** — a DNS proxy that extracts features per query and
   runs the model **compiled to native Go** (via `m2cgen`), so routing adds
   no per-query subprocess or IPC overhead.

> The model is compiled *into* the Go binary (`engine/rf_model.go`). There is no
> Python-at-request-time. (An earlier design called a `predict_dns.py`
> subprocess per query; that was removed — it was never wired up and would have
> dominated latency.)

---

## ⚙️ Prerequisites

* **Python 3.10+** — telemetry, training, analysis
* **Go 1.18+** — the proxy engine
* `pip install -r requirements.txt`
  (`m2cgen` is only needed to *re-export* the Go model; everything else runs
  without it.)

---

## 🚀 Workflow: Scan → Train → **Evaluate** → Deploy

> **Prefer a GUI?** `python3 gui/app.py` opens a desktop app (standard-library
> Tkinter, no extra deps) to edit resolvers/domains, run a **watchable** scan,
> and view the data summary + full evaluation. It's a thin front-end over the
> same modules below — identical data and analysis, nothing re-implemented.

### Phase 1 — Collect telemetry
```bash
python3 telemetry/scanner.py --probes 3
```
Probes each resolver for each domain **3× and keeps the median** (de-noises
WiFi jitter), recording success and latency separately into
`data/raw_probes.csv`. Run it across **many hours of the day** if you want to
test the time-of-day hypothesis — the bundled data only covers 21:00–22:00.

### Phase 2 — Evaluate the hypothesis (the important step)
```bash
python3 analysis/evaluate.py
```
Out-of-fold cross-validated comparison of every routing policy on success rate,
effective-latency percentiles, and regret, with bootstrap confidence intervals
and a clear verdict. Writes `results/metrics.csv` and plots to `results/`.
**Run this before claiming ML helps.**

### Phase 3 — Train & export the model
```bash
python3 ml/trainer.py
```
Trains on noise-resistant labels, reports CV accuracy against the no-skill
majority floor + feature importances, saves `ml/artifact.pkl`, and (if `m2cgen`
is installed) regenerates `engine/rf_model.go`.

### Phase 4 — Launch the engine
```bash
cd engine && go mod tidy && go build
sudo ./hybrid-dns        # binds the UDP port from config.json (default 53)
```
Set your OS resolver to `127.0.0.1` to route real traffic through it.

---

## 📂 Project structure
```
AlphaDNS/
├── config.json              # resolvers map {id: ip} + listen port (shared by Go & Python)
├── data/
│   ├── domains.csv          # target domains to probe
│   └── raw_probes.csv       # telemetry output (gitignored)
├── telemetry/
│   └── scanner.py           # multi-probe resolver telemetry collector
├── ml/
│   ├── dataset.py           # SHARED feature/label contract (single source of truth)
│   ├── trainer.py           # trains + exports the model, reports honest signal
│   └── artifact.pkl         # trained sklearn model (gitignored)
├── analysis/
│   └── evaluate.py          # policy comparison harness  ← the research deliverable
├── results/                 # metrics.csv + plots (generated)
├── gui/                     # Tkinter desktop app (stdlib) — edit/scan/evaluate
│   └── app.py               # run: python3 gui/app.py
└── engine/
    ├── main.go              # DNS proxy: feature extraction, forwarding, SERVFAIL
    ├── predictor.go         # packs features → calls the compiled scorer
    └── rf_model.go          # m2cgen-exported Random Forest (gitignored; regenerated by trainer)
```

## 🔬 Variables
* **Dependent:** resolution success rate; effective latency (p50/p95/p99, where a
  failure costs a 2000 ms timeout penalty).
* **Policies compared:** static-ISP, static-anycast (Cloudflare/Google/Quad9),
  random (lower bound), oracle (upper bound), ML hybrid.

## ⚠️ Known limitations (read before citing results)
* **Temporal coverage:** bundled data is two adjacent hours only — the diurnal
  congestion hypothesis is **untestable** with it. Re-scan across the day.
* **Measurement noise:** collected over WiFi; multi-probe medians help but a
  wired LAN run is strongly preferred for latency claims.
* **Feature signal:** TLD / subdomain-depth / hour have little causal link to
  which resolver is fastest. The oracle shows real latency headroom (151 vs
  199 ms mean), but capturing it needs **live** features (per-resolver latency
  EWMA, recent failure rate), not static ones. See [CLAUDE.md](CLAUDE.md).
