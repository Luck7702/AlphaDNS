"""AlphaDNS shared dataset / feature / label contract.

This module is the single source of truth for:
  * which features the model consumes (FEATURES) and in which order,
  * how raw probe data is loaded and normalised,
  * how routing *labels* are derived from measured latencies.

Both ``ml/trainer.py`` (which trains + exports the model) and
``analysis/evaluate.py`` (which measures whether the model helps) import
from here so the two can never drift apart.

------------------------------------------------------------------------
Why the label is NOT simply "the fastest resolver"
------------------------------------------------------------------------
The original pipeline labelled every query with ``argmin(latency)`` and
asked the model to predict it. On real (WiFi-collected) data that target
is dominated by measurement noise: the fastest of two resolvers that are
within ~10 ms of each other flips on essentially every re-probe, so there
is nothing learnable. The dominant, *stable* signal is instead whether a
resolver **resolves the query at all** -- some upstreams (a local ISP
resolver, a filtering resolver like Quad9) fail a large fraction of
queries while anycast resolvers do not.

We therefore model an "effective latency" that folds failure and speed
into one cost, and derive a robust label that prefers globally-reliable
resolvers among near-ties. See :func:`make_robust_labels`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --- Paths -------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_FILE = os.path.join(ROOT_DIR, "data", "raw_probes.csv")
CONFIG_FILE = os.path.join(ROOT_DIR, "config.json")

# --- The feature contract (ORDER MATTERS) ------------------------------
# This order must match, byte for byte, the slice the Go engine builds in
# engine/predictor.go (input[0..3]). If you add/reorder a feature here you
# MUST update extractFeatures() + the m2cgen input indexing in Go.
FEATURES = ["is_global_tld", "is_id_tld", "subdomain_depth", "hour"]

# Latency (ms) assigned to a query that failed / timed out. It doubles as
# the sentinel the legacy scanner wrote into the latency columns, and as
# the penalty an "effective latency" pays for a failure.
FAIL_MS = 2000.0


def load_resolvers(config_file: str = CONFIG_FILE) -> dict[str, str]:
    """Return the ``{id: ip}`` resolver map from config.json."""
    with open(config_file) as fh:
        return json.load(fh).get("resolvers", {})


def resolver_ids(config_file: str = CONFIG_FILE) -> list[str]:
    """Resolver ids ("0".."3") in sorted, stable order."""
    return sorted(load_resolvers(config_file).keys(), key=int)


@dataclass
class ProbeData:
    """Normalised view of a probe dataset.

    Attributes
    ----------
    df:        the raw rows (one per probed query), columns cleaned.
    features:  ``df[FEATURES]`` as a float DataFrame.
    latency:   (n, k) effective-latency matrix; failures == FAIL_MS.
    success:   (n, k) boolean matrix; True where that resolver resolved.
    resolvers: resolver ids aligned with the matrix columns.
    """

    df: pd.DataFrame
    features: pd.DataFrame
    latency: np.ndarray
    success: np.ndarray
    resolvers: list[str]

    def __len__(self) -> int:  # number of probed queries
        return len(self.df)


def load_probes(path: str = DATA_FILE, config_file: str = CONFIG_FILE) -> ProbeData:
    """Load + normalise a probe CSV into a :class:`ProbeData`.

    Handles two on-disk schemas transparently:

    * **legacy** -- a ``{id}_latency`` column per resolver where a value
      ``>= FAIL_MS`` encodes "failed" (what the old scanner wrote);
    * **new** -- an additional ``{id}_success`` column per resolver and a
      latency that is NaN/blank on failure (what the rewritten scanner
      writes). When present, ``{id}_success`` is authoritative.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    ids = resolver_ids(config_file)

    lat = np.empty((len(df), len(ids)), dtype=float)
    succ = np.empty((len(df), len(ids)), dtype=bool)
    for j, rid in enumerate(ids):
        lat_col = f"{rid}_latency"
        if lat_col not in df.columns:
            raise ValueError(f"probe file {path!r} missing column {lat_col!r}")
        col = pd.to_numeric(df[lat_col], errors="coerce")
        succ_col = f"{rid}_success"
        if succ_col in df.columns:
            ok = df[succ_col].astype(str).str.lower().isin({"1", "true", "yes"})
        else:  # legacy: a sentinel latency marks the failure
            ok = col.notna() & (col < FAIL_MS)
        succ[:, j] = ok.to_numpy()
        # effective latency: real value when ok, otherwise the failure penalty
        eff = col.where(ok, FAIL_MS).fillna(FAIL_MS)
        lat[:, j] = eff.to_numpy()

    # Make sure every feature column exists, deriving it from the domain
    # when an older file is missing it (keeps the contract self-healing).
    _ensure_features(df)

    return ProbeData(
        df=df.reset_index(drop=True),
        features=df[FEATURES].astype(float).reset_index(drop=True),
        latency=lat,
        success=succ,
        resolvers=ids,
    )


def _ensure_features(df: pd.DataFrame) -> None:
    """Backfill any missing FEATURES column from the ``domain`` field."""
    if "domain" in df.columns:
        dom = df["domain"].astype(str)
        if "is_global_tld" not in df.columns:
            df["is_global_tld"] = dom.str.endswith((".com", ".net", ".org")).astype(int)
        if "is_id_tld" not in df.columns:
            df["is_id_tld"] = dom.str.endswith(".id").astype(int)
        if "subdomain_depth" not in df.columns:
            # number of dots -- MUST match the Go engine (len(labels) - 1)
            df["subdomain_depth"] = dom.str.count(r"\.").astype(int)
    if "hour" not in df.columns:
        df["hour"] = 0
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"cannot build features {missing} (no 'domain' column?)")


def make_robust_labels(
    data: ProbeData, tol_ms: float = 15.0
) -> tuple[np.ndarray, np.ndarray]:
    """Derive a noise-resistant routing label for every query.

    For each query we take the set of resolvers whose effective latency is
    within ``tol_ms`` of the row's best (i.e. the resolvers that are, given
    measurement noise, "as good as the winner"). Among that candidate set
    we pick the resolver with the highest *global* success rate, breaking
    further ties by lowest *global* mean effective latency.

    The effect: instead of chasing the per-probe argmin (which flips on
    noise), the label consistently prefers the resolver that is reliably
    good across the whole dataset. Rows where every resolver fails keep the
    globally-most-reliable resolver as a least-bad fallback.

    Returns ``(labels, oracle)`` where ``labels`` is the robust target and
    ``oracle`` is the per-row argmin (the un-regularised upper bound used
    by the evaluator).
    """
    lat = data.latency
    n, k = lat.shape

    # Global quality of each resolver: reliability first, then speed.
    global_success = data.success.mean(axis=0)  # (k,)
    global_eff = lat.mean(axis=0)               # (k,)
    # Rank key: prefer high success, then low latency. Lower = better.
    quality = (-global_success, global_eff)

    oracle = np.argmin(lat, axis=1)
    labels = np.empty(n, dtype=int)
    row_best = lat.min(axis=1)
    for i in range(n):
        within = np.where(lat[i] <= row_best[i] + tol_ms)[0]
        # choose the globally-best resolver among the near-ties
        best = min(within, key=lambda j: (quality[0][j], quality[1][j]))
        labels[i] = best
    return labels, oracle
