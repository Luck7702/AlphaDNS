"""Scan tab -- a watchable run of the real telemetry scanner.

Reuses ``telemetry/scanner.run_scan`` (the same concurrency engine the CLI
uses) and the same ``scan_domain`` / ``probe_header``, so data collected here
is byte-identical to CLI data. The scan runs on a worker thread; rows are
written + flushed there and pushed to the Tk thread for display via a queue.
"""

from __future__ import annotations

import csv
import os
import random
import queue
import tkinter as tk
from tkinter import ttk, messagebox

import services


class ScanTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.worker = services.Worker()
        self._ids: list[str] = []
        self._resolvers: dict = {}
        self._success: dict = {}
        self._build()

    # -- layout ---------------------------------------------------------------
    def _build(self) -> None:
        ctl = ttk.Frame(self); ctl.pack(anchor="w", fill="x")
        self.probes = tk.StringVar(value="3")
        self.timeout = tk.StringVar(value="1.0")
        self.workers = tk.StringVar(value="8")
        self.limit = tk.StringVar(value="")
        for label, var, w in (("Probes", self.probes, 5), ("Timeout s", self.timeout, 6),
                              ("Workers", self.workers, 5), ("First N (blank=all)", self.limit, 8)):
            ttk.Label(ctl, text=label + ":").pack(side="left", padx=(0, 2))
            ttk.Entry(ctl, textvariable=var, width=w).pack(side="left", padx=(0, 10))
        self.start_btn = ttk.Button(ctl, text="Start scan", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(ctl, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left")

        ttk.Label(self, justify="left", wraplength=900, foreground="#666",
                  text=("Appends to data/raw_probes.csv. Higher workers finish faster but "
                        "let queries contend — use 1 for a rigorous latency claim.")
                  ).pack(anchor="w", pady=(6, 4))

        self.prog = ttk.Progressbar(self, mode="determinate")
        self.prog.pack(fill="x", pady=4)

        body = ttk.Frame(self); body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, show="headings", height=16)
        ys = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.tree.tag_configure("allfail", foreground="#c0392b")
        self.tree.tag_configure("somefail", foreground="#b9770e")

        self.status = ttk.Label(self, text="Idle.", foreground="#1a7a4b")
        self.status.pack(anchor="w", pady=(6, 0))

    def _configure_columns(self, ids: list[str]) -> None:
        cols = ["domain"] + [f"r{rid}" for rid in ids] + ["best"]
        self.tree.config(columns=cols)
        self.tree.heading("domain", text="domain")
        self.tree.column("domain", width=220, anchor="w")
        for rid in ids:
            self.tree.heading(f"r{rid}", text=f"{rid} ({self._resolvers.get(rid, '?')})")
            self.tree.column(f"r{rid}", width=120, anchor="center")
        self.tree.heading("best", text="best")
        self.tree.column("best", width=140, anchor="w")
        self.tree.delete(*self.tree.get_children())

    # -- run ------------------------------------------------------------------
    def _start(self) -> None:
        if self.worker.running():
            return
        try:
            probes, timeout = int(self.probes.get()), float(self.timeout.get())
            workers = int(self.workers.get())
            limit = int(self.limit.get()) if self.limit.get().strip() else None
        except ValueError:
            messagebox.showerror("Scan", "Probes/workers must be integers and timeout a number.")
            return

        try:
            import scanner  # telemetry/scanner.py (needs dnspython)
        except Exception as exc:
            messagebox.showerror(
                "dnspython missing",
                f"The scanner needs dnspython:\n\n    pip install dnspython\n\n({exc})")
            return

        config = services.load_config()
        self._resolvers = config.get("resolvers", {})
        if not self._resolvers:
            messagebox.showerror("Scan", "config.json has no resolvers. Add some on the Resolvers tab.")
            return
        self._ids = sorted(self._resolvers, key=int)

        domains = self._load_domains()
        if not domains:
            messagebox.showerror("Scan", "data/domains.csv is empty. Add domains on the Domains tab.")
            return
        random.shuffle(domains)
        if limit:
            domains = domains[:limit]

        self._configure_columns(self._ids)
        self._success = {rid: 0 for rid in self._ids}
        self.prog.config(maximum=len(domains), value=0)
        self._set_running(True)
        self.status.config(text=f"Scanning {len(domains)} domains × {len(self._ids)} resolvers…")

        self.worker.start(self._do_scan, scanner, domains, probes, timeout, workers)
        self.after(100, self._pump)

    def _do_scan(self, scanner, domains, probes, timeout, workers) -> None:
        """Runs on the worker thread: write the CSV, stream rows to the queue."""
        out = services.PROBES_FILE
        os.makedirs(os.path.dirname(out), exist_ok=True)
        is_empty = (not os.path.exists(out)) or os.stat(out).st_size == 0
        with open(out, "a", newline="") as fh:
            w = csv.writer(fh)
            if is_empty:
                w.writerow(scanner.probe_header(self._ids))

            def on_result(done, total, row, optimal, cells):
                w.writerow(row)
                fh.flush()
                self.worker.q.put(("row", (done, total, row, optimal)))

            scanner.run_scan(domains, self._resolvers, self._ids,
                             probes=probes, timeout=timeout, workers=workers,
                             on_result=on_result, should_stop=self.worker.should_stop)

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.worker.q.get_nowait()
                if kind == "row":
                    self._add_row(*payload)
                elif kind == "error":
                    messagebox.showerror("Scan error", payload)
                elif kind == "done":
                    self._set_running(False)
                    stopped = self.worker.should_stop()
                    self.status.config(text=("Stopped." if stopped else "Scan complete.") +
                                       f"  → {services.PROBES_FILE}")
                    return
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _add_row(self, done, total, row, optimal) -> None:
        vals = [row[0]]
        all_fail = True
        for j, rid in enumerate(self._ids):
            lat, succ = row[6 + 2 * j], row[7 + 2 * j]
            ok = str(succ) in ("1", "True", "true")
            vals.append(f"{lat}ms" if ok else "FAIL")
            if ok:
                all_fail = False
                self._success[rid] += 1
        any_fail = "FAIL" in vals[1:]
        vals.append(f"{optimal} ({self._resolvers.get(optimal, '?')})")
        tag = "allfail" if all_fail else ("somefail" if any_fail else "")
        item = self.tree.insert("", "end", values=vals, tags=(tag,) if tag else ())
        self.tree.see(item)
        self.prog.config(value=done)
        self.status.config(text=f"{done}/{total}   ·   " +
                           "   ".join(f"{rid}:{self._success[rid]}ok" for rid in self._ids))

    # -- helpers --------------------------------------------------------------
    def _load_domains(self) -> list[str]:
        if not os.path.exists(services.DOMAINS_FILE):
            return []
        with open(services.DOMAINS_FILE) as fh:
            lines = [ln.strip() for ln in fh]
        if lines and lines[0].lower() == "domain":
            lines = lines[1:]
        return [ln for ln in lines if ln]

    def _stop(self) -> None:
        self.worker.stop()
        self.status.config(text="Stopping… (letting in-flight probes drain)")

    def _set_running(self, running: bool) -> None:
        self.start_btn.config(state="disabled" if running else "normal")
        self.stop_btn.config(state="normal" if running else "disabled")
