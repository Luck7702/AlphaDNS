# AlphaDNS — How to Use It & Read the Results

A plain-language guide. If the README is the "what" and CLAUDE.md is for the AI,
**this file is the "how do I actually run this and what do the numbers mean."**

---

## 0. One-time setup

```bash
pip install -r requirements.txt
```

Two of those packages are only needed for specific steps, and the program tells
you if they're missing — so don't worry if install is fussy:

- **dnspython** → only to *collect* new data (Step 1).
- **m2cgen** → only to *rebuild the Go model* (Step 3). The analysis works without it.

You can run the analysis (Step 2) with just pandas + scikit-learn + matplotlib,
on the data already in the repo.

---

## The big picture: 4 steps

```
   Step 1                Step 2                 Step 3              Step 4
 ┌─────────┐         ┌──────────────┐        ┌──────────┐       ┌──────────┐
 │  SCAN   │  ──────▶│   EVALUATE   │ ─────▶ │  TRAIN   │ ────▶ │  DEPLOY  │
 │ collect │  data   │ does ML even │  yes?  │ + export │ model │ run the  │
 │  data   │  .csv   │   help?      │        │ to Go    │       │  proxy   │
 └─────────┘         └──────────────┘        └──────────┘       └──────────┘
```

**The most important step is Step 2 (Evaluate).** It answers your research
question. Always run it before you believe ML routing helps.

You do **not** have to run Step 1 to try this — the repo already ships with
collected data, so you can jump straight to Step 2.

---

## Step 1 — Collect data (optional; needs internet + dnspython)

```bash
python3 telemetry/scanner.py --probes 3
```

What it does: for every domain in `data/domains.csv`, it asks each of your 4
resolvers (defined in `config.json`) to look it up **3 times**, and records the
**median** time plus whether it succeeded. Results append to
`data/raw_probes.csv`.

- `--probes 3` = probe each 3× and take the median (cuts random WiFi noise).
  Bump to `--probes 5` for cleaner data.
- Press **Ctrl-C** anytime; whatever it collected so far is saved.
- **Tip:** run it at different times of day (morning, noon, night). The current
  bundled data is only from 21:00–22:00, which is why "time of day" can't really
  be tested yet.

You can skip this step entirely and use the existing data.

---

## Step 2 — Evaluate (the important one)

```bash
python3 analysis/evaluate.py
```

This trains the model on part of the data, tests it on data it **hasn't seen**,
and compares it against simple strategies. It prints a table, saves
`results/metrics.csv`, and draws 3 charts in `results/`.

### Reading the table

Here's the real output on the bundled data, annotated:

```
                         success_%  mean_eff_ms   p50_ms   p95_ms   p99_ms  mean_ok_ms  regret_ms
static_0 (103.88.88.88)      73.31       658.94   203.28  2000.00  2000.00      170.80     507.80
static_1 (1.1.1.1)           95.47       214.58   102.12   816.35  2000.00      129.90      63.44
static_2 (8.8.8.8)           95.47       198.62   100.35   805.51  2000.00      113.19      47.48
static_3 (9.9.9.9)           80.83       576.90   258.12  2000.00  2000.00      239.36     425.77
random                       86.13       421.38   117.75  2000.00  2000.00      167.11     270.25
ML hybrid                    95.47       198.61   100.35   805.51  2000.00      113.18      47.47
oracle                       95.66       151.14    44.62   307.48  2000.00       67.35       0.00
```

**The rows (each is a routing strategy):**
| row | meaning |
|---|---|
| `static_0..3` | "always use this one resolver." `0`=your ISP, `1`=Cloudflare, `2`=Google, `3`=Quad9. This is the normal, non-ML world. |
| `random` | pick a resolver at random. A sanity floor — anything useful should beat this. |
| `ML hybrid` | **your model**, scored only on queries it didn't train on. |
| `oracle` | a cheater that always picks the truly-best resolver in hindsight. Impossible to beat; it shows the absolute ceiling. |

**The columns (lower = better, except success):**
| column | meaning | in plain words |
|---|---|---|
| `success_%` | % of queries that got a valid answer | **higher is better.** Did you get an answer at all? |
| `mean_eff_ms` | average latency, where a **failure counts as 2000 ms** | the single best summary number: blends speed + reliability |
| `p50_ms` | median (typical) effective latency | half your queries are faster than this |
| `p95_ms` | the slow 5% | "when it's slow, how slow?" |
| `p99_ms` | the slowest 1% | the worst tail |
| `mean_ok_ms` | average latency counting **only successful** queries | raw speed, ignoring failures |
| `regret_ms` | how far above the oracle (0 = perfect) | "how much did this strategy leave on the table?" |

### How to actually interpret this example

1. **Look at `success_%` first.** ISP (`static_0`) answers only **73%** of the
   time — it drops 1 in 4 queries! Quad9 (`static_3`) is 81%. Cloudflare and
   Google are ~95%. *Reliability is the big story here, not speed.*

2. **`p99_ms` is 2000 for everyone** — even the oracle. That's because ~4.3% of
   domains fail on *every* resolver (dead domains / blocked / network), and a
   failure is charged 2000 ms. No resolver choice can fix a domain that nobody
   can resolve. So ignore p99 here and look at p95.

3. **Compare `ML hybrid` to the best `static_` row.** They're basically
   identical (198.61 vs 198.62, 95.47% vs 95.47%). The model learned to "always
   pick a reliable anycast resolver" — which is sensible, but it means ML isn't
   adding anything a fixed good resolver wasn't already giving you.

4. **`oracle` shows there *is* headroom** (151 ms vs 199 ms, p95 307 vs 806) —
   a perfect chooser would be faster. But that headroom comes from knowing which
   resolver happens to be fastest *right now*, which the current features
   (TLD / depth / hour) simply can't predict.

### The verdict line

Right after the table:

```
=== ML hybrid vs best static baseline (static_2 (8.8.8.8)) ===
  success rate delta :  +0.00 pp   95% CI [+0.00, +0.00]
  mean eff. latency  :  -0.01 ms   95% CI [-0.31, +0.28]
  verdict            : No statistically significant gain over the best static baseline ...
```

- **delta** = ML minus the best fixed resolver. Here ≈ 0.
- **95% CI** = the range the true difference probably lives in. **If the CI
  includes 0, the two are tied** — any difference is noise.
- Plain reading: *on this data, ML routing is no better than just always using
  Google.* That's an honest, legitimate result — not a bug.

### The "Model signal" section

```
  majority-label share (no-skill accuracy floor): 69.9%
  feature importances:
     hour               0.389
     subdomain_depth    0.315
     ...
```

- **Majority floor 69.9%** = if the model *always* guessed the single most
  common answer, it'd be right 69.9% of the time. If the model's accuracy (shown
  by `trainer.py`, ~69.8%) is about the same, **the model isn't really learning
  — it's just guessing the popular answer.** That's the case here.
- **Feature importances** = which inputs the model leans on. `hour` looks
  important, but remember the data only has 2 hours in it, so that's misleading —
  another reason to collect data across the whole day.

### The charts (in `results/`)

- **`latency_cdf.png`** — curves climbing left-to-right. A curve that's higher
  and more to the **left** is better (more queries answered quickly). The oracle
  hugs the top-left; ISP/Quad9 lag.
- **`success_by_arm.png`** — bar chart of reliability per strategy. Easiest way
  to *see* that the ISP resolver is the weak one.
- **`feature_importance.png`** — what the model uses (same caveat as above).

---

## Step 3 — Train & export the model

```bash
python3 ml/trainer.py
```

Trains the final model on all your data, prints how much real signal it has,
saves `ml/artifact.pkl`, and — **if `m2cgen` is installed** — writes the model
into `engine/rf_model.go` so the Go proxy can use it.

If you see `m2cgen not installed`, just run `pip install m2cgen` and re-run. The
training itself still worked; only the Go export was skipped.

---

## Step 4 — Deploy the live proxy

```bash
cd engine
go build
sudo ./hybrid-dns       # needs sudo because it binds a low UDP port (53)
```

Then point your computer's DNS to `127.0.0.1` to send real traffic through it.
Each query gets logged with the resolver the model chose. (Edit the listen port
in `config.json` if you don't want to use 53 / don't want sudo.)

---

## "So does the ML actually help?" — a decision checklist

After running **Step 2**, you have a positive result **only if all three hold**:

1. `ML hybrid` `success_%` is **clearly higher** than the best `static_` row, **and/or**
   `ML hybrid` `mean_eff_ms` is **clearly lower**, and
2. the **verdict** says "ML beats the best static baseline beyond noise"
   (the 95% CI does **not** cross zero), and
3. it beats `random` comfortably (sanity check).

On the current bundled data, #2 fails — so the honest conclusion is *"a single
reliable anycast resolver is good enough; ML didn't add measurable value yet."*
To change that, the model needs **features that actually predict speed** (live
per-resolver latency/failure history) and **data across many hours** — see the
"future direction" note in `CLAUDE.md`.

---

## Troubleshooting

| symptom | fix |
|---|---|
| `raw_probes.csv not found` | run Step 1, or use the bundled data (it's already there) |
| `No module named 'dns'` | `pip install dnspython` (only needed for Step 1) |
| `m2cgen not installed` | `pip install m2cgen` (only needed to rebuild the Go model) |
| `matplotlib unavailable; skipping plots` | harmless — the table + CSV still print; `pip install matplotlib` for charts |
| engine won't bind port 53 | run with `sudo`, or change `"port"` in `config.json` to e.g. 5300 |
| changed features/labels but Go acts the same | re-run `ml/trainer.py` (with m2cgen) then `go build` — the model is compiled in |
