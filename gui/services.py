"""Shared glue for the AlphaDNS Tkinter GUI.

Deliberately thin: project paths + import bootstrap, config.json IO, a small
threaded ``Worker`` that talks to the Tk main loop through a queue, and an
instant dataset summary that *reuses* ``ml/dataset.py``. No DNS feature,
success, latency or label logic lives here -- it all comes from the existing
modules, so the GUI can never drift from the feature contract.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading

# --- project paths -----------------------------------------------------------
GUI_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(GUI_DIR)
CONFIG_FILE = os.path.join(ROOT_DIR, "config.json")
DOMAINS_FILE = os.path.join(ROOT_DIR, "data", "domains.csv")
PROBES_FILE = os.path.join(ROOT_DIR, "data", "raw_probes.csv")
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

# Make the sibling script dirs importable the same way evaluate.py/trainer.py
# do (they are namespace dirs -- no __init__.py). Done at import so any tab can
# lazily ``import dataset`` / ``import scanner`` / ``import evaluate``.
for _p in (os.path.join(ROOT_DIR, "ml"),
           os.path.join(ROOT_DIR, "analysis"),
           os.path.join(ROOT_DIR, "telemetry")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# --- config.json -------------------------------------------------------------
def load_config() -> dict:
    with open(CONFIG_FILE) as fh:
        return json.load(fh)


def save_config(config: dict) -> None:
    """Write config.json pretty-printed with a trailing newline (git-friendly)."""
    with open(CONFIG_FILE, "w") as fh:
        json.dump(config, fh, indent=4)
        fh.write("\n")


# --- threading: run work off the Tk thread, report back via a queue ----------
class Worker:
    """Run a callable in a background thread, funnelling messages to the UI.

    The target pushes ``(kind, payload)`` tuples onto ``self.q``; the Tk side
    drains the queue from a ``root.after`` pump and never touches a widget
    off-thread. ``should_stop`` lets long jobs cancel cooperatively.
    """

    def __init__(self):
        self.q: "queue.Queue" = queue.Queue()
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, target, *args, **kwargs) -> None:
        self._stop.clear()

        def run():
            try:
                target(*args, **kwargs)
            except Exception as exc:  # surface it; never crash the UI
                self.q.put(("error", repr(exc)))
            finally:
                self.q.put(("done", None))

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    def should_stop(self) -> bool:
        return self._stop.is_set()

    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


# --- instant dataset summary (reuses ml/dataset.py) --------------------------
def data_summary(path: str = PROBES_FILE) -> dict:
    """Per-resolver + global stats for the Results tab.

    A pure read via ``dataset.load_probes`` -- nothing is recomputed here.
    Raises if the CSV is missing/unreadable; the caller reports it.
    """
    import numpy as np
    import dataset as ds  # ml/dataset.py (on sys.path above)

    data = ds.load_probes(path)
    resolvers = ds.load_resolvers()
    n, k = data.latency.shape

    rows = []
    for j, rid in enumerate(data.resolvers):
        ok = data.success[:, j]
        rows.append({
            "id": rid,
            "ip": resolvers.get(rid, "?"),
            "success_pct": float(ok.mean()) * 100.0,
            "median_ms": float(np.median(data.latency[ok, j])) if ok.any() else float("nan"),
        })

    any_ok = data.success.any(axis=1)
    return {
        "n": n,
        "k": k,
        "hours": int(data.df["hour"].nunique()) if "hour" in data.df else 0,
        "resolvers": rows,
        "all_fail_pct": float((~any_ok).mean()) * 100.0,
        "oracle_mean_ms": float(data.latency.min(axis=1).mean()),
        "best_static_mean_ms": float(min(data.latency[:, j].mean() for j in range(k))),
    }
