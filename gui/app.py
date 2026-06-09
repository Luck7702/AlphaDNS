"""AlphaDNS desktop GUI -- Tkinter, standard library only.

A thin front-end over the existing modules: edit the resolver map and the
domain list, run a watchable scan (``telemetry/scanner.run_scan``), and read
results (``ml/dataset`` + ``analysis/evaluate``). It computes no DNS features,
success, latency or metrics itself -- those all come from the real modules so
the GUI stays faithful to the research pipeline.

Run:  python3 gui/app.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import services  # noqa: F401  (imported first: bootstraps sys.path for ml/analysis/telemetry)
from resolvers_tab import ResolversTab
from domains_tab import DomainsTab
from scan_tab import ScanTab
from results_tab import ResultsTab


def main() -> None:
    root = tk.Tk()
    root.title("AlphaDNS")
    root.geometry("980x660")
    root.minsize(840, 560)

    try:  # a slightly less dated default theme where available
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
    for label, cls in (("Resolvers", ResolversTab),
                       ("Domains", DomainsTab),
                       ("Scan", ScanTab),
                       ("Results", ResultsTab)):
        nb.add(cls(nb), text=label)

    ttk.Label(root, text=f"AlphaDNS  ·  {services.ROOT_DIR}",
              anchor="w", relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")

    root.mainloop()


if __name__ == "__main__":
    main()
