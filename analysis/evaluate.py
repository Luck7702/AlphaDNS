"""AlphaDNS routing evaluation -- the headline research instrument.

Question this script answers
----------------------------
Does ML-based per-query resolver selection actually beat a static
single-resolver policy on **resolution success** and **latency**?

How it answers it honestly
--------------------------
Comparing a model's predictions against the same data it trained on is
circular, so every ML decision here is produced **out of fold**: the data
is split with stratified K-fold cross-validation, the model is trained on
K-1 folds and asked to route the held-out fold, and we record the latency
/ success it *actually achieved* on those unseen queries. We then compare
that policy against:

  * ``static_<id>``  -- always use one fixed resolver (the deployed status quo),
  * ``random``       -- uniform random choice (a lower bound),
  * ``oracle``       -- the per-query best resolver (an unbeatable upper bound).

For each policy we report resolution success rate, mean / p50 / p95 / p99
"effective latency" (a failed query costs FAIL_MS), and mean regret versus
the oracle. Finally we bootstrap a 95% CI on the ML-minus-best-static
deltas so the reader can see whether any difference is real or just noise.

Run: ``python3 analysis/evaluate.py``  (writes a table + CSV + plots to results/).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml"))
import dataset as ds  # noqa: E402  (path set above)

RESULTS_DIR = os.path.join(ds.ROOT_DIR, "results")
RNG = np.random.default_rng(42)
N_SPLITS = 5
N_ESTIMATORS = 15  # kept small to match what is exported to Go
MAX_DEPTH = 10


# --------------------------------------------------------------------------
# Policies: each returns, per query, the index of the chosen resolver column.
# --------------------------------------------------------------------------
def ml_out_of_fold(data: ds.ProbeData, labels: np.ndarray) -> np.ndarray:
    """Out-of-fold ML routing decisions (one unseen decision per query)."""
    X = data.features.to_numpy()
    chosen = np.empty(len(data), dtype=int)

    # Stratified CV needs every class to appear >= n_splits times; shrink
    # the fold count if a rare label would otherwise break stratification.
    counts = np.bincount(labels)
    nonzero = counts[counts > 0]
    n_splits = max(2, min(N_SPLITS, int(nonzero.min())))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    for train_idx, test_idx in skf.split(X, labels):
        clf = RandomForestClassifier(
            n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH, random_state=42
        )
        clf.fit(X[train_idx], labels[train_idx])
        pred = clf.predict(X[test_idx])
        # model predicts a resolver *id-position*; labels are column indices
        chosen[test_idx] = pred.astype(int)
    return chosen


def static_choice(data: ds.ProbeData, col: int) -> np.ndarray:
    return np.full(len(data), col, dtype=int)


def random_choice(data: ds.ProbeData) -> np.ndarray:
    return RNG.integers(0, data.latency.shape[1], size=len(data))


def oracle_choice(data: ds.ProbeData) -> np.ndarray:
    return np.argmin(data.latency, axis=1)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def achieved(data: ds.ProbeData, choice: np.ndarray):
    """(effective_latency, success) actually obtained by a choice vector."""
    rows = np.arange(len(data))
    return data.latency[rows, choice], data.success[rows, choice]


def metrics(data: ds.ProbeData, choice: np.ndarray, oracle_eff: np.ndarray) -> dict:
    eff, succ = achieved(data, choice)
    ok = eff[succ]  # latencies of the queries that actually resolved
    return {
        "success_%": succ.mean() * 100,
        "mean_eff_ms": eff.mean(),
        "p50_ms": np.percentile(eff, 50),
        "p95_ms": np.percentile(eff, 95),
        "p99_ms": np.percentile(eff, 99),
        "mean_ok_ms": ok.mean() if ok.size else float("nan"),
        "regret_ms": (eff - oracle_eff).mean(),
    }


def bootstrap_delta(
    data: ds.ProbeData, ml: np.ndarray, base: np.ndarray, n: int = 2000
):
    """95% CI for (ML - static_base) on success rate and mean effective latency."""
    ml_eff, ml_succ = achieved(data, ml)
    bs_eff, bs_succ = achieved(data, base)
    m = len(data)
    d_succ = np.empty(n)
    d_eff = np.empty(n)
    for b in range(n):
        idx = RNG.integers(0, m, size=m)
        d_succ[b] = (ml_succ[idx].mean() - bs_succ[idx].mean()) * 100
        d_eff[b] = ml_eff[idx].mean() - bs_eff[idx].mean()
    pct = lambda a: (np.percentile(a, 2.5), np.percentile(a, 97.5))
    return {
        "d_success_pp": (d_succ.mean(), *pct(d_succ)),
        "d_mean_eff_ms": (d_eff.mean(), *pct(d_eff)),
    }


# --------------------------------------------------------------------------
# Plots (optional -- skipped cleanly if matplotlib is unavailable)
# --------------------------------------------------------------------------
def make_plots(data, choices, names, importances):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"[i] matplotlib unavailable ({exc}); skipping plots.")
        return

    # 1. Effective-latency CDF per policy (clipped so the failure spike at
    #    FAIL_MS doesn't crush the interesting 0-400 ms region).
    fig, ax = plt.subplots(figsize=(8, 5))
    for name in names:
        eff, _ = achieved(data, choices[name])
        xs = np.sort(eff)
        ys = np.arange(1, len(xs) + 1) / len(xs)
        ax.plot(np.clip(xs, 0, 600), ys, label=name, linewidth=1.6)
    ax.set(xlabel="effective latency (ms, clipped at 600)",
           ylabel="cumulative fraction of queries",
           title="DNS resolution latency by routing policy")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(RESULTS_DIR, "latency_cdf.png"), dpi=120)
    plt.close(fig)

    # 2. Success rate per policy
    fig, ax = plt.subplots(figsize=(8, 5))
    vals = [achieved(data, choices[n])[1].mean() * 100 for n in names]
    ax.bar(names, vals, color="#3b7dd8")
    ax.set(ylabel="resolution success rate (%)", title="Resolution success by policy")
    ax.set_ylim(0, 100)
    for i, v in enumerate(vals):
        ax.text(i, v + 1, f"{v:.1f}", ha="center", fontsize=9)
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout(); fig.savefig(os.path.join(RESULTS_DIR, "success_by_arm.png"), dpi=120)
    plt.close(fig)

    # 3. Feature importances
    fig, ax = plt.subplots(figsize=(7, 4))
    order = np.argsort(importances)
    ax.barh(np.array(ds.FEATURES)[order], importances[order], color="#48a868")
    ax.set(xlabel="Gini importance", title="What the model actually uses")
    fig.tight_layout(); fig.savefig(os.path.join(RESULTS_DIR, "feature_importance.png"), dpi=120)
    plt.close(fig)
    print(f"[i] plots written to {RESULTS_DIR}/")


# --------------------------------------------------------------------------
def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    data = ds.load_probes()
    resolver_map = ds.load_resolvers()
    labels, oracle = ds.make_robust_labels(data)
    oracle_eff, _ = achieved(data, oracle)

    print(f"[*] Loaded {len(data)} probed queries across {data.latency.shape[1]} resolvers "
          f"({data.df['hour'].nunique()} distinct hour(s) of day).")
    print(f"[*] All-resolvers-fail queries (irreducible): "
          f"{(~data.success.any(axis=1)).mean()*100:.1f}%\n")

    # Build every policy's per-query choice vector.
    choices: dict[str, np.ndarray] = {}
    for j, rid in enumerate(data.resolvers):
        ip = resolver_map.get(rid, "?")
        choices[f"static_{rid} ({ip})"] = static_choice(data, j)
    choices["random"] = random_choice(data)
    choices["ML hybrid"] = ml_out_of_fold(data, labels)
    choices["oracle"] = oracle_choice(data)
    names = list(choices)

    # Per-policy metrics table.
    rows = {n: metrics(data, choices[n], oracle_eff) for n in names}
    table = pd.DataFrame(rows).T
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.2f}")
    print("=== Routing policy comparison (out-of-fold for ML) ===")
    print(table.to_string())
    table.to_csv(os.path.join(RESULTS_DIR, "metrics.csv"))

    # Honest verdict: ML vs the BEST static baseline (lowest mean effective latency).
    static_names = [n for n in names if n.startswith("static_")]
    best_static = min(static_names, key=lambda n: rows[n]["mean_eff_ms"])
    ci = bootstrap_delta(data, choices["ML hybrid"], choices[best_static])
    print(f"\n=== ML hybrid vs best static baseline ({best_static}) ===")
    ds_mean, ds_lo, ds_hi = ci["d_success_pp"]
    de_mean, de_lo, de_hi = ci["d_mean_eff_ms"]
    print(f"  success rate delta : {ds_mean:+6.2f} pp   95% CI [{ds_lo:+.2f}, {ds_hi:+.2f}]")
    print(f"  mean eff. latency  : {de_mean:+6.2f} ms   95% CI [{de_lo:+.2f}, {de_hi:+.2f}]")
    succ_sig = ds_lo > 0 or ds_hi < 0
    lat_sig = de_lo > 0 or de_hi < 0
    verdict = (
        "ML beats the best static baseline beyond noise."
        if (succ_sig and ds_mean > 0) or (lat_sig and de_mean < 0)
        else "No statistically significant gain over the best static baseline "
             "(the CI crosses zero). On this data a single reliable anycast "
             "resolver already captures the available benefit."
    )
    print(f"  verdict            : {verdict}")

    # Model signal: a final model on all data for importances + an honest
    # accuracy reference against the 'always predict the majority label' rule.
    clf = RandomForestClassifier(n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH, random_state=42)
    clf.fit(data.features.to_numpy(), labels)
    majority = np.bincount(labels).max() / len(labels)
    ml_choice_eff, _ = achieved(data, choices["ML hybrid"])
    print(f"\n=== Model signal ===")
    print(f"  majority-label share (no-skill accuracy floor): {majority*100:.1f}%")
    print("  feature importances:")
    for feat, imp in sorted(zip(ds.FEATURES, clf.feature_importances_), key=lambda t: -t[1]):
        print(f"     {feat:18} {imp:.3f}")

    make_plots(data, choices, names, clf.feature_importances_)
    print(f"\n[*] Done. Metrics -> {os.path.join(RESULTS_DIR, 'metrics.csv')}")


if __name__ == "__main__":
    main()
