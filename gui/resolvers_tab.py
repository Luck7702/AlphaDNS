"""Resolvers tab -- edit the config.json resolver map + listen port.

config.json is the single source of truth shared by the scanner, the model and
the Go engine. This tab just round-trips it; it does not touch any data.
"""

from __future__ import annotations

import ipaddress
import tkinter as tk
from tkinter import ttk, messagebox

import services


class ResolversTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.config_data: dict = {}
        self._build()
        self._reload()

    # -- layout ---------------------------------------------------------------
    def _build(self) -> None:
        ttk.Label(self, justify="left", wraplength=900,
                  text=("Resolver map shared by the scanner, the model and the Go engine. "
                        "The id is the position the model predicts; the IP is where that "
                        "position routes.")).pack(anchor="w")
        ttk.Label(self, justify="left", wraplength=900, foreground="#a85400",
                  text=("⚠  Changing a resolver's IP changes what its data column means. "
                        "Start a FRESH data/raw_probes.csv and retrain before serving — "
                        "don't mix old and new resolver data under the same id.")
                  ).pack(anchor="w", pady=(4, 10))

        self.tree = ttk.Treeview(self, columns=("id", "ip"), show="headings", height=8)
        self.tree.heading("id", text="ID")
        self.tree.heading("ip", text="Resolver IP")
        self.tree.column("id", width=80, anchor="center")
        self.tree.column("ip", width=260, anchor="w")
        self.tree.pack(anchor="w")
        self.tree.bind("<Double-1>", lambda e: self._edit())

        row = ttk.Frame(self); row.pack(anchor="w", pady=6)
        ttk.Button(row, text="Add", command=self._add).pack(side="left")
        ttk.Button(row, text="Edit", command=self._edit).pack(side="left", padx=4)
        ttk.Button(row, text="Remove", command=self._remove).pack(side="left")

        port = ttk.Frame(self); port.pack(anchor="w", pady=(10, 4))
        ttk.Label(port, text="Listen port:").pack(side="left")
        self.port_var = tk.StringVar()
        ttk.Entry(port, textvariable=self.port_var, width=8).pack(side="left", padx=6)

        act = ttk.Frame(self); act.pack(anchor="w", pady=10)
        ttk.Button(act, text="Reload", command=self._reload).pack(side="left")
        ttk.Button(act, text="Save config.json", command=self._save).pack(side="left", padx=6)
        self.status = ttk.Label(self, text="", foreground="#1a7a4b")
        self.status.pack(anchor="w")

    # -- data -----------------------------------------------------------------
    def _reload(self) -> None:
        try:
            self.config_data = services.load_config()
        except Exception as exc:
            messagebox.showerror("config.json", f"Could not load config.json:\n{exc}")
            self.config_data = {"resolvers": {}, "port": 53}
        self.tree.delete(*self.tree.get_children())
        resolvers = self.config_data.get("resolvers", {})
        for rid in sorted(resolvers, key=lambda x: int(x) if str(x).isdigit() else 1 << 30):
            self.tree.insert("", "end", values=(rid, resolvers[rid]))
        self.port_var.set(str(self.config_data.get("port", 53)))
        self.status.config(text="Loaded.")

    def _ids(self) -> set[str]:
        return {self.tree.set(i, "id") for i in self.tree.get_children()}

    def _next_id(self) -> str:
        used = {int(v) for v in self._ids() if v.isdigit()}
        n = 0
        while n in used:
            n += 1
        return str(n)

    # -- add / edit / remove --------------------------------------------------
    def _add(self) -> None:
        result = self._dialog("Add resolver", self._next_id(), "")
        if result:
            self.tree.insert("", "end", values=result)

    def _edit(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        rid, ip = self.tree.item(sel[0], "values")
        result = self._dialog("Edit resolver", rid, ip)
        if result:
            self.tree.item(sel[0], values=result)

    def _remove(self) -> None:
        for i in self.tree.selection():
            self.tree.delete(i)

    def _dialog(self, title: str, rid: str, ip: str):
        """Modal 2-field prompt. Returns (id, ip) validated, or None."""
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        id_var, ip_var = tk.StringVar(value=rid), tk.StringVar(value=ip)
        ttk.Label(win, text="ID (integer):").grid(row=0, column=0, sticky="e", padx=8, pady=6)
        ttk.Entry(win, textvariable=id_var, width=10).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(win, text="Resolver IP:").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        ip_entry = ttk.Entry(win, textvariable=ip_var, width=22)
        ip_entry.grid(row=1, column=1, sticky="w", padx=8)
        ip_entry.focus_set()

        out: dict = {}

        def ok():
            new_id, new_ip = id_var.get().strip(), ip_var.get().strip()
            if not new_id.isdigit():
                messagebox.showerror(title, "ID must be a non-negative integer.", parent=win)
                return
            try:
                ipaddress.ip_address(new_ip)
            except ValueError:
                messagebox.showerror(title, f"'{new_ip}' is not a valid IP address.", parent=win)
                return
            if new_id != rid and new_id in self._ids():
                messagebox.showerror(title, f"ID {new_id} already exists.", parent=win)
                return
            out["v"] = (new_id, new_ip)
            win.destroy()

        bar = ttk.Frame(win); bar.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(bar, text="OK", command=ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="left")
        win.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        self.wait_window(win)
        return out.get("v")

    # -- save -----------------------------------------------------------------
    def _save(self) -> None:
        resolvers = {self.tree.set(i, "id"): self.tree.set(i, "ip")
                     for i in self.tree.get_children()}
        if not resolvers:
            messagebox.showerror("config.json", "At least one resolver is required.")
            return
        port_str = self.port_var.get().strip()
        if not port_str.isdigit() or not (0 < int(port_str) < 65536):
            messagebox.showerror("config.json", "Port must be an integer in 1..65535.")
            return

        ids_changed = resolvers != services.load_config().get("resolvers", {})
        if ids_changed and not messagebox.askyesno(
                "Heads up",
                "You changed the resolver map.\n\nFor honest data, start a fresh "
                "data/raw_probes.csv and retrain before serving — old probes were "
                "measured against the previous resolvers.\n\nSave config.json now?"):
            return

        self.config_data["resolvers"] = resolvers
        self.config_data["port"] = int(port_str)
        try:
            services.save_config(self.config_data)
        except Exception as exc:
            messagebox.showerror("config.json", f"Could not write config.json:\n{exc}")
            return
        self.status.config(text=f"Saved {len(resolvers)} resolvers, port {port_str}.")
