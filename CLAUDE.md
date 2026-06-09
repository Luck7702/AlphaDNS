# CLAUDE.md — orientation for AI assistants working on AlphaDNS

Read this before changing anything. It records the decisions and invariants
that the code alone won't tell you.

## What this project is

A research prototype testing one hypothesis: *does ML-based per-query DNS
resolver selection beat a static single resolver on latency + resolution
success, for Indonesian networks?* **AlphaDNS is also its own evaluation
harness.** The goal is an honest answer, not a demo that "proves" ML wins.

**Current answer (on bundled data): no, not significantly.** A single reliable
anycast resolver (Google/Cloudflare) already matches the oracle. Do not "fix"
this by massaging the evaluation toward a positive result — the negative result
is the credible finding. If new data changes it, let the harness say so.

### Why the result is negative (the mechanism)
- Resolution **success** is the dominant axis. ISP resolver fails 27%, Quad9
  19%; Cloudflare/Google fail ~4.5% and hit the 95.7% oracle success ceiling.
- Among reliable resolvers, **latency is noise**: the fastest flips on 62% of
  repeat probes. Static features (TLD, depth, hour) have no causal link to it.
- So the model correctly collapses to "always pick a reliable anycast
  resolver," and is statistically tied with the best static baseline.

### What would actually make ML pay off (future direction)
The oracle shows real latency headroom (mean 151 vs 199 ms). Capturing it needs
**live** features the model doesn't yet have: per-resolver latency EWMA, recent
failure rate, time-of-day with real diurnal coverage (bundled data is only
21:00–22:00). Adding those is the scientifically promising path — not tuning the
existing TLD/depth/hour features.

## The ONE invariant you must not break: the feature contract

Training and serving must compute identical features, in identical order:

| feature | Python (scanner + `ml/dataset.py`) | Go (`engine/main.go extractFeatures`) |
|---|---|---|
| `is_global_tld` | ends with .com/.net/.org | same (note Go names have trailing `.`) |
| `is_id_tld` | ends with .id | same |
| `subdomain_depth` | `domain.count('.')` | `len(labels) - 1` ← **must equal count('.')** |
| `hour` | integer hour | `time.Now().Hour()` (integer, **not** fractional) |

Order is defined once in `ml/dataset.py:FEATURES` and must match the slice built
in `engine/predictor.go` and the `input[0..3]` indexing in the generated
`engine/rf_model.go`. Two historical bugs lived here: `subdomain_depth` was
`len(parts)` (off by one) and `hour` was fractional (`hour + min/60`), which
crossed tree split boundaries at X.5. Don't reintroduce them.

## Architecture decisions

- **Model is compiled into Go** (`m2cgen` → `engine/rf_model.go`), not called as
  a Python subprocess. A per-query subprocess would dominate DNS latency and
  defeat the purpose. The old `ml/predict_dns.py` subprocess was dead code and
  was removed.
- **`config.json` is shared** by Go and Python (resolver map + listen port).
  Resolver ids are strings `"0".."3"`; the model predicts an id-position and the
  engine maps it back to an IP.
- **Failure vs latency are distinct.** `ml/dataset.py:FAIL_MS = 2000.0` is both
  the legacy failure sentinel and the penalty a failed query pays in "effective
  latency." Never average raw latency columns without separating success first;
  `load_probes()` does this and handles both the legacy and new CSV schemas.
- **Robust labels** (`make_robust_labels`): the target is *not* per-probe
  argmin (noise). Among resolvers within `tol_ms` of the row's best, pick the
  one with the highest global success rate. This de-noises the training target.

## File map

- `ml/dataset.py` — **single source of truth** for features, labels, loading.
  Import it; don't re-implement feature logic elsewhere.
- `analysis/evaluate.py` — the deliverable. Out-of-fold CV comparison of all
  routing policies + bootstrap CIs + plots. Run this to (dis)prove the thesis.
- `ml/trainer.py` — trains, reports honest signal vs majority floor, exports Go.
- `telemetry/scanner.py` — multi-probe (median) telemetry collector. `run_scan`
  is the shared concurrency engine (CLI `main()` and the GUI both call it);
  `probe_header` defines the CSV schema in one place. Don't duplicate either.
- `engine/` — Go DNS proxy. `main.go` (proxy + features + SERVFAIL),
  `predictor.go` (feature packing), `rf_model.go` (generated, gitignored).
- `gui/` — Tkinter desktop front-end (stdlib only). A thin presentation layer:
  it imports `dataset` / `scanner` / `evaluate` and computes no features,
  success, latency or metrics itself. `app.py` is the entry point.

## Running things

```bash
pip install -r requirements.txt          # dnspython, m2cgen optional at runtime
python3 telemetry/scanner.py --probes 3  # collect (needs dnspython + network)
python3 analysis/evaluate.py             # evaluate (needs only the CSV)
python3 ml/trainer.py                    # train + export (Go export needs m2cgen)
cd engine && go build && ./hybrid-dns    # run the proxy
python3 gui/app.py                       # desktop GUI: edit/scan/evaluate (stdlib Tkinter)
```

- `analysis/evaluate.py` and `ml/trainer.py` run on the **existing CSV** with no
  network and no m2cgen. Good for iterating on the analysis.
- After changing labels/features in `ml/dataset.py`, re-run `trainer.py` (with
  m2cgen) to regenerate `engine/rf_model.go`, then rebuild the engine.

## Gotchas

- `engine/rf_model.go` and `data/raw_probes.csv` and `ml/artifact.pkl` are
  gitignored (generated). A fresh clone must run scan + train before the engine
  has a model to compile.
- `go build` in `engine/` drops a `hybrid-dns` binary; don't commit it.
- The bundled `raw_probes.csv` was collected over WiFi and fluctuates; treat its
  absolute latencies cautiously. Prefer a wired re-scan for any latency claim.
- **Never append a scan onto a `raw_probes.csv` written with a different schema or
  resolver set.** The scanner writes the header only when the file is empty, so a
  schema change silently appends mismatched rows; `pandas` then refuses the whole
  file ("Expected N fields … saw M") and `evaluate.py`/`trainer.py`/the GUI all
  break. When the schema or resolver map changes, start a fresh file.
