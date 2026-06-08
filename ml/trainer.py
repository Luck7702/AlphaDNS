"""Train the AlphaDNS resolver-selection model and export it to Go.

Pipeline
--------
1. Load + normalise probe data via :mod:`dataset` (shared contract).
2. Build noise-resistant routing labels (``dataset.make_robust_labels``).
3. Report *honest* model signal: stratified cross-validated accuracy
   measured against the no-skill majority-label floor, plus feature
   importances. (If CV accuracy ~= the majority floor, the features carry
   no signal -- see analysis/evaluate.py for whether that still helps.)
4. Fit the final model on all data, persist ``artifact.pkl``, and export a
   native Go scorer to ``engine/rf_model.go`` via m2cgen.

Run: ``python3 ml/trainer.py``

Note: the exported Go scorer consumes features in the exact order of
``dataset.FEATURES``. The Go engine (engine/predictor.go) MUST build its
input slice in that same order, or training/serving will silently diverge.
"""

from __future__ import annotations

import os
import sys

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dataset as ds  # noqa: E402

GO_OUTPUT_FILE = os.path.join(ds.ROOT_DIR, "engine", "rf_model.go")
ARTIFACT_FILE = os.path.join(ds.BASE_DIR, "artifact.pkl")

N_ESTIMATORS = 15  # small enough for a compact Go export, big enough to be an ensemble
MAX_DEPTH = 10


def train_and_export() -> None:
    print(f"[*] Loading dataset from {ds.DATA_FILE} ...")
    try:
        data = ds.load_probes()
    except FileNotFoundError:
        print("[!] raw_probes.csv not found. Run telemetry/scanner.py first.")
        return

    X = data.features.to_numpy()
    y, _ = ds.make_robust_labels(data)
    print(f"[*] {len(data)} samples | features = {ds.FEATURES}")

    # --- Honest signal check ------------------------------------------------
    counts = np.bincount(y, minlength=data.latency.shape[1])
    majority = counts.max() / len(y)
    n_splits = max(2, min(5, int(counts[counts > 0].min())))
    clf = RandomForestClassifier(n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH, random_state=42)
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    acc = cross_val_score(clf, X, y, cv=cv, scoring="accuracy")
    print(f"[*] Label distribution (by resolver id): "
          f"{dict(zip(data.resolvers, counts.tolist()))}")
    print(f"[*] {n_splits}-fold CV accuracy : {acc.mean()*100:5.1f}% (+/- {acc.std()*100:.1f})")
    print(f"[*] No-skill majority floor : {majority*100:5.1f}%")
    if acc.mean() <= majority + 0.02:
        print("[i] CV accuracy is at/near the majority floor: the features carry "
              "little routing signal. This is expected for TLD/depth/hour vs. "
              "latency -- see analysis/evaluate.py for the policy-level impact.")

    # --- Fit final model + feature importances -----------------------------
    clf.fit(X, y)
    print("[*] Feature importances:")
    for feat, imp in sorted(zip(ds.FEATURES, clf.feature_importances_), key=lambda t: -t[1]):
        print(f"      {feat:18} {imp:.3f}")

    joblib.dump(clf, ARTIFACT_FILE)
    print(f"[*] Saved sklearn artifact -> {ARTIFACT_FILE}")

    # --- Export native Go scorer (optional dependency) ---------------------
    try:
        import m2cgen as m2c
    except ImportError:
        print("[!] m2cgen not installed; skipped Go export. "
              "Install it (`pip install m2cgen`) and re-run to regenerate "
              f"{os.path.relpath(GO_OUTPUT_FILE, ds.ROOT_DIR)}.")
        return

    go_code = m2c.export_to_go(clf)
    if not go_code.startswith("package main"):
        go_code = "package main\n\n" + go_code
    with open(GO_OUTPUT_FILE, "w") as fh:
        fh.write(go_code)
    print(f"[*] SUCCESS: Go scorer exported -> {GO_OUTPUT_FILE}")
    print("    Rebuild the engine (`cd engine && go build`) to pick it up.")


if __name__ == "__main__":
    train_and_export()
