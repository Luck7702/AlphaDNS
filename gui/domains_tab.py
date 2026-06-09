"""Domains tab -- edit data/domains.csv, the scan target list.

A plain newline-separated list (with a leading ``domain`` header, which the
scanner skips). No DNS logic here -- just text editing + dedupe/sort.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import services


class DomainsTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self._build()
        self._reload()

    # -- layout ---------------------------------------------------------------
    def _build(self) -> None:
        ttk.Label(self, justify="left", wraplength=900,
                  text=("One domain per line. Saved to data/domains.csv (the 'domain' "
                        "header is written for you). This is the list the scanner probes.")
                  ).pack(anchor="w")

        bar = ttk.Frame(self); bar.pack(anchor="w", pady=8)
        ttk.Button(bar, text="Reload", command=self._reload).pack(side="left")
        ttk.Button(bar, text="Dedupe & sort", command=self._dedupe).pack(side="left", padx=4)
        ttk.Button(bar, text="Import file…", command=self._import).pack(side="left")
        ttk.Button(bar, text="Save", command=self._save).pack(side="left", padx=4)
        self.count = ttk.Label(bar, text=""); self.count.pack(side="left", padx=14)

        wrap = ttk.Frame(self); wrap.pack(fill="both", expand=True)
        self.text = tk.Text(wrap, wrap="none", undo=True, height=20)
        ys = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=ys.set, font=("TkFixedFont", 10))
        self.text.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.text.bind("<KeyRelease>", lambda e: self._update_count())

        self.status = ttk.Label(self, text="", foreground="#1a7a4b")
        self.status.pack(anchor="w", pady=(6, 0))

    # -- helpers --------------------------------------------------------------
    def _domains(self) -> list[str]:
        return [d.strip() for d in self.text.get("1.0", "end").splitlines() if d.strip()]

    def _set_domains(self, domains: list[str]) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(domains))
        self._update_count()

    def _update_count(self) -> None:
        self.count.config(text=f"{len(self._domains())} domains")

    # -- actions --------------------------------------------------------------
    def _reload(self) -> None:
        domains: list[str] = []
        if os.path.exists(services.DOMAINS_FILE):
            with open(services.DOMAINS_FILE) as fh:
                lines = [ln.strip() for ln in fh]
            if lines and lines[0].lower() == "domain":
                lines = lines[1:]
            domains = [ln for ln in lines if ln]
        self._set_domains(domains)
        self.status.config(text=f"Loaded {len(domains)} domains.")

    def _dedupe(self) -> None:
        domains = sorted({d.lower() for d in self._domains()})
        self._set_domains(domains)
        self.status.config(text=f"Deduped & sorted → {len(domains)} domains (not yet saved).")

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            title="Import domains",
            filetypes=[("Text/CSV", "*.txt *.csv"), ("All files", "*.*")])
        if not path:
            return
        with open(path) as fh:
            extra = [ln.strip() for ln in fh
                     if ln.strip() and ln.strip().lower() != "domain"]
        cur = self._domains()
        self.text.insert("end", ("\n" if cur else "") + "\n".join(extra))
        self._update_count()
        self.status.config(text=f"Imported {len(extra)} lines (not yet saved).")

    def _save(self) -> None:
        domains = self._domains()
        if not domains:
            messagebox.showerror("domains.csv", "The domain list is empty.")
            return
        os.makedirs(os.path.dirname(services.DOMAINS_FILE), exist_ok=True)
        with open(services.DOMAINS_FILE, "w") as fh:
            fh.write("domain\n")
            fh.write("\n".join(domains) + "\n")
        self.status.config(text=f"Saved {len(domains)} domains to data/domains.csv")
