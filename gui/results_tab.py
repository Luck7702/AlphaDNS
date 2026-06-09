"""Results tab -- read the data and run the real evaluation.

Two actions, both reusing existing code so there is no second, divergent
analysis path:

* **Data Summary** -- instant per-resolver success/latency from
  ``services.data_summary`` (which calls ``ml/dataset.load_probes``).
* **Run Full Analysis** -- runs ``analysis/evaluate.main`` (out-of-fold CV +
  bootstrap CI + plots) on a worker thread, then surfaces its real outputs:
  the printed verdict, ``results/metrics.csv``, and the PNGs it wrote.
"""

from __future__ import annotations

import os
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

import services

PLOTS = ("latency_cdf.png", "success_by_arm.png", "feature_importance.png")


class ResultsTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.worker = services.Worker()
        self._imgs: list = []  # keep PhotoImage refs alive
        self._build()

    # -- layout ---------------------------------------------------------------
    def _build(self) -> None:
        bar = ttk.Frame(self); bar.pack(anchor="w", fill="x")
        ttk.Button(bar, text="Data Summary", command=self._summary).pack(side="left")
        self.analyze_btn = ttk.Button(bar, text="Run Full Analysis (CV)", command=self._analyze)
        self.analyze_btn.pack(side="left", padx=6)
        self.headline = ttk.Label(bar, text="", foreground="#333")
        self.headline.pack(side="left", padx=12)

        self.tree = ttk.Treeview(self, show="headings", height=8)
        self.tree.pack(fill="x", pady=8)

        split = ttk.Panedwindow(self, orient="vertical")
        split.pack(fill="both", expand=True)

        txt_frame = ttk.Frame(split)
        self.text = ScrolledText(txt_frame, height=10, font=("TkFixedFont", 9), wrap="word")
        self.text.pack(fill="both", expand=True)
        split.add(txt_frame, weight=1)

        # scrollable image area for the plots
        plot_frame = ttk.Frame(split)
        self.canvas = tk.Canvas(plot_frame, highlightthickness=0)
        psc = ttk.Scrollbar(plot_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=psc.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        psc.pack(side="right", fill="y")
        self.plot_host = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.plot_host, anchor="nw")
        self.plot_host.bind("<Configure>",
                            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        split.add(plot_frame, weight=2)

        self.status = ttk.Label(self, text="", foreground="#1a7a4b")
        self.status.pack(anchor="w")

    def _show_table(self, columns, rows) -> None:
        self.tree.config(columns=columns)
        for c in columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=max(90, 60 + len(c) * 7), anchor="center")
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", values=r)

    # -- data summary ---------------------------------------------------------
    def _summary(self) -> None:
        try:
            s = services.data_summary()
        except FileNotFoundError:
            messagebox.showinfo("Data Summary", "No data/raw_probes.csv yet — run a scan first.")
            return
        except Exception as exc:
            messagebox.showerror("Data Summary", f"Could not summarise the data:\n{exc}")
            return
        rows = [(r["id"], r["ip"], f"{r['success_pct']:.1f}",
                 "—" if r["median_ms"] != r["median_ms"] else f"{r['median_ms']:.1f}")
                for r in s["resolvers"]]
        self._show_table(("id", "ip", "success %", "median ms (ok)"), rows)
        self.headline.config(
            text=(f"{s['n']} queries · {s['hours']} hour(s) · all-resolvers-fail "
                  f"{s['all_fail_pct']:.1f}% · oracle {s['oracle_mean_ms']:.0f}ms "
                  f"vs best-static {s['best_static_mean_ms']:.0f}ms"))
        self.status.config(text="Data summary from data/raw_probes.csv.")

    # -- full analysis --------------------------------------------------------
    def _analyze(self) -> None:
        if self.worker.running():
            return
        self.analyze_btn.config(state="disabled")
        self.status.config(text="Running out-of-fold CV + bootstrap… (this can take a moment)")
        self.text.delete("1.0", "end")
        self.worker.start(self._run_eval)
        self.after(150, self._pump)

    def _run_eval(self) -> None:
        """Worker thread: run the real evaluator, capturing its stdout."""
        import io
        import contextlib
        import evaluate  # analysis/evaluate.py (heavy: sklearn/pandas)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            evaluate.main()
        self.worker.q.put(("analysis", buf.getvalue()))

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.worker.q.get_nowait()
                if kind == "analysis":
                    self.text.insert("end", payload)
                    self._load_metrics()
                    self._load_plots()
                elif kind == "error":
                    messagebox.showerror("Analysis error", payload)
                    self.status.config(text="Analysis failed.")
                elif kind == "done":
                    self.analyze_btn.config(state="normal")
                    if not self.status.cget("text").endswith("failed."):
                        self.status.config(text="Analysis complete — metrics + plots from results/.")
                    return
        except queue.Empty:
            pass
        self.after(150, self._pump)

    def _load_metrics(self) -> None:
        path = os.path.join(services.RESULTS_DIR, "metrics.csv")
        if not os.path.exists(path):
            return
        try:
            import pandas as pd
            df = pd.read_csv(path, index_col=0)
        except Exception:
            return
        columns = ["policy"] + [str(c) for c in df.columns]
        rows = [[idx] + [f"{v:.2f}" if isinstance(v, float) else v for v in row]
                for idx, row in zip(df.index, df.to_numpy())]
        self._show_table(columns, rows)

    def _load_plots(self) -> None:
        for child in self.plot_host.winfo_children():
            child.destroy()
        self._imgs.clear()
        shown = 0
        for name in PLOTS:
            path = os.path.join(services.RESULTS_DIR, name)
            if not os.path.exists(path):
                continue
            try:
                img = tk.PhotoImage(file=path)
            except Exception:
                ttk.Label(self.plot_host, text=f"{name} (saved to results/)").pack(anchor="w")
                continue
            self._imgs.append(img)
            ttk.Label(self.plot_host, text=name, font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
            ttk.Label(self.plot_host, image=img).pack(anchor="w", pady=(0, 8))
            shown += 1
        if shown == 0:
            ttk.Label(self.plot_host,
                      text="No plots (matplotlib unavailable?) — numbers above are authoritative."
                      ).pack(anchor="w")
