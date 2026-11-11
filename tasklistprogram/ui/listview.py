# listview.py
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from . import theme

class TaskListView:
    # TITLE first so group headers are flush-left; ID last
    COLS = ("title","due","rem","prio","rep","notes","times","id")
    HEADERS = {
        "title":"TITLE", "due":"DUE", "rem":"REM", "prio":"PRIO", "rep":"REPEAT",
        "notes":"NOTES", "times":"TIMES", "id":"ID"
    }
    WIDTHS = {"title":460,"due":180,"rem":60,"prio":90,"rep":110,"notes":300,"times":80,"id":60}
    COL_MIN = {"title":240,"due":140,"rem":36,"prio":70,"rep":90,"notes":160,"times":60,"id":40}
    COL_MAX = {"title":740,"due":260,"rem":60,"prio":110,"rep":160,"notes":420,"times":90,"id":70}

    def __init__(self, master, on_request_edit, request_refresh, palette=None):
        self.master = master
        self.on_request_edit = on_request_edit
        self.request_refresh = request_refresh
        self.palette = palette or theme.LIGHT

        # Expansion state
        self._expanded = {"_UNGROUPED_": True}
        self._expanded_default = True  # default expansion for unknown groups

        # Wrap frame + vertical scrollbar
        self.wrap = ttk.Frame(master)
        self.wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.tree = ttk.Treeview(
            self.wrap, columns=self.COLS, show="headings", height=20, selectmode="extended"
        )
        for c in self.COLS:
            self.tree.heading(c, text=self.HEADERS[c])
            self.tree.column(c, width=self.WIDTHS[c], anchor=tk.W)
        self.vsb = ttk.Scrollbar(self.wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Styles
        self._default_font = tkfont.nametofont("TkDefaultFont")
        self._group_font = self._default_font.copy()
        self._group_font.configure(size=max(9, self._default_font.cget("size")), weight="bold")
        self.apply_palette(self.palette)

        self.tree.bind("<Double-1>", self._on_double_click)

    def apply_palette(self, palette):
        """(Re)configure row/tag colors from a theme palette. Safe to call on toggle."""
        self.palette = palette
        prio = palette["prio"]
        for code in ("U", "H", "M", "L", "D", "X"):
            self.tree.tag_configure(f"prio_{code}", background=prio[code])
        # Configured after the priority tags so the muted foreground wins for these rows.
        self.tree.tag_configure("deleted", foreground=palette["muted_fg"])
        self.tree.tag_configure("suspended", foreground=palette["muted_fg"])
        # Neutral header bar so group rows never read as a colored (esp. blue Misc) task row.
        self.tree.tag_configure(
            "group_header",
            background=palette["group_bg"],
            foreground=palette["group_fg"],
            font=self._group_font,
        )

    # ----- selection helpers -----
    def selected_task_ids(self):
        ids = []
        id_idx = self.COLS.index("id")
        for iid in self.tree.selection():
            if self.identify_row_kind(iid) != "task":
                continue
            vals = self.tree.item(iid)["values"]
            if vals and len(vals) > id_idx:
                try:
                    ids.append(int(vals[id_idx]))
                except Exception:
                    pass
        return ids

    def identify_row_kind(self, iid):
        if not iid:
            return "none"
        tags = set(self.tree.item(iid, "tags") or [])
        if "group_header" in tags:
            return "header"
        vals = self.tree.item(iid)["values"]
        if not vals:
            return "none"
        id_idx = self.COLS.index("id")
        if len(vals) > id_idx:
            try:
                int(vals[id_idx])
                return "task"
            except Exception:
                return "none"
        return "none"

    # ----- rendering -----
    def render(self, tasks, scope, prio_icon, reminder_chip_fn, grouped: bool):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.tree.heading("due", text=("DELETED" if scope == "deleted" else "DUE"))

        if not grouped:
            for t in tasks:
                self._insert_task_row(t, scope, prio_icon, reminder_chip_fn)
            self._autosize_columns()
            return

        by_group, ungrouped = {}, []
        for t in tasks:
            g = (t.get("group") or "").strip()
            if g:
                by_group.setdefault(g, []).append(t)
            else:
                ungrouped.append(t)

        group_names = sorted(by_group.keys(), key=lambda s: s.lower())

        for gname in group_names:
            expanded = self._expanded.get(gname, self._expanded_default)
            caret = "▼" if expanded else "▶"
            self._insert_group_header(gname, caret)
            if expanded:
                for t in by_group[gname]:
                    self._insert_task_row(t, scope, prio_icon, reminder_chip_fn)

        if ungrouped:
            ug_expanded = self._expanded.get("_UNGROUPED_", self._expanded_default)
            ug_caret = "▼" if ug_expanded else "▶"
            self._insert_group_header("Ungrouped", ug_caret, iid="g::_UNGROUPED_")
            if ug_expanded:
                for t in ungrouped:
                    self._insert_task_row(t, scope, prio_icon, reminder_chip_fn)

        self._autosize_columns()

    # ----- global expand/collapse -----
    def expand_all(self):
        self._expanded_default = True
        for k in list(self._expanded.keys()):
            self._expanded[k] = True

    def collapse_all(self):
        self._expanded_default = False
        for k in list(self._expanded.keys()):
            self._expanded[k] = False

    def is_default_expanded(self):
        return bool(self._expanded_default)

    # ----- internals -----
    def _insert_group_header(self, gname, caret, iid=None):
        vals = [""] * len(self.COLS)
        vals[self.COLS.index("title")] = f"{caret}  {gname}"
        self.tree.insert("", tk.END, values=tuple(vals), tags=("group_header",), iid=(iid or f"g::{gname}"))

    def _insert_task_row(self, t, scope, prio_icon, reminder_chip_fn):
        due = t.get("deleted_at", "") if scope == "deleted" else t.get("due", "")
        prio = prio_icon.get((t.get("priority","M") or "M").upper(), t.get("priority","M"))
        display_title = t.get("_display_title", t.get("title",""))
        row_map = {
            "title": display_title,
            "due": due,
            "rem": (reminder_chip_fn(t) if callable(reminder_chip_fn) else ""),
            "prio": prio,
            "rep": t.get("repeat",""),
            "notes": t.get("notes",""),
            "times": t.get("times_completed",0),
            "id": t["id"],
        }
        vals = tuple(row_map[c] for c in self.COLS)
        tags = ["task_row"]
        p = t.get("priority")
        if p: tags.append(f"prio_{p.upper()}")
        if t.get("is_deleted"): tags.append("deleted")
        if t.get("is_suspended"): tags.append("suspended")
        self.tree.insert("", tk.END, values=vals, tags=tuple(tags))

    def _autosize_columns(self):
        font = tkfont.nametofont("TkDefaultFont")
        pad = 18
        rows = list(self.tree.get_children())
        for col in self.COLS:
            texts = [self.HEADERS[col]]
            idx = self.COLS.index(col)
            for iid in rows:
                vals = self.tree.item(iid)["values"]
                if not vals or len(vals) <= idx:
                    continue
                txt = str(vals[idx])
                if col in ("title","notes") and len(txt) > 80:
                    txt = txt[:80] + "…"
                texts.append(txt)
            if not texts:
                continue
            max_px = max(font.measure(t) for t in texts) + pad
            target = max(self.COL_MIN[col], min(max_px, self.COL_MAX[col]))
            self.tree.column(col, width=target)

    # ----- interaction -----
    def _on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        kind = self.identify_row_kind(iid)
        if kind == "header":
            if iid == "g::_UNGROUPED_":
                self._expanded["_UNGROUPED_"] = not self._expanded.get("_UNGROUPED_", self._expanded_default)
            else:
                try:
                    _, gname = iid.split("g::", 1)
                except ValueError:
                    gname = ""
                if gname:
                    self._expanded[gname] = not self._expanded.get(gname, self._expanded_default)
            self.request_refresh()
            return
        if kind == "task":
            self.on_request_edit()
            return
        return
