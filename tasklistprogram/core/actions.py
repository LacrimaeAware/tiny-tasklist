# actions_mixin.py
import logging
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date, datetime, timedelta

from .dates import parse_due_entry, fmt_due_for_store, parse_stored_due, add_months_dateonly, next_due
from .model import save_db
from .documents import append_journal_task
from ..ui.controls import AutoCompleteEntry

logger = logging.getLogger(__name__)

class ActionsMixin:
    def mark_done(self):
        sel_ids = [t["id"] for t in self.selected_tasks()]
        logger.debug("mark_done selected ids: %s", sel_ids)

        for t in self.selected_tasks():
            before_due = t.get("due", "")
            rep = (t.get("repeat") or "none").lower()

            # mark this cycle complete
            t["completed_at"] = datetime.now().isoformat(timespec="seconds")
            t["times_completed"] = t.get("times_completed", 0) + 1
            t.setdefault("history", []).append(date.today().isoformat())
            t["skip_count"] = 0
            if "base_priority" in t:
                t["priority"] = t.get("base_priority", t.get("priority", "M"))
                t.pop("base_priority", None)

            append_journal_task(t.get("title", ""))

            if rep != "none":
                cur = t.get("due", "")
                due_dt = parse_stored_due(cur) or datetime.now()

                had_time = isinstance(cur, str) and len(cur) > 10
                next_day = next_due(due_dt.date(), rep)

                if had_time:
                    new_dt = datetime.combine(next_day, due_dt.time())
                    t["due"] = new_dt.strftime("%Y-%m-%d %H:%M")
                else:
                    t["due"] = next_day.strftime("%Y-%m-%d")

                # refresh as a checklist for next cycle
                t["completed_at"] = ""

            after_due = t.get("due", "")
            logger.debug(
                "mark_done id=%s rep=%s due: %r -> %r completed_at=%r",
                t["id"], rep, before_due, after_due, t.get("completed_at"),
            )

        save_db(self.db)
        self.refresh()

    def soft_delete(self):
        ids = [t["id"] for t in self.selected_tasks()]
        logger.debug("soft delete ids: %s", ids)
        ts = datetime.now().isoformat(timespec="seconds")
        for t in self.selected_tasks():
            t["is_deleted"] = True
            t["deleted_at"] = ts
        save_db(self.db)
        self.refresh()

    def restore(self):
        ids = [t["id"] for t in self.selected_tasks()]
        logger.debug("restore ids: %s", ids)
        for t in self.selected_tasks():
            t["is_deleted"] = False
            t.pop("deleted_at", None)
        save_db(self.db)
        self.refresh()

    def suspend_tasks(self):
        changed = False
        for t in self.selected_tasks():
            if not t.get("is_suspended"):
                t["is_suspended"] = True
                changed = True
        if changed:
            save_db(self.db)
            self.refresh()

    def unsuspend_tasks(self):
        changed = False
        for t in self.selected_tasks():
            if t.get("is_suspended"):
                t["is_suspended"] = False
                changed = True
        if changed:
            save_db(self.db)
            self.refresh()

    def hard_delete(self):
        sels = self.selected_tasks()
        if not sels:
            return
        ids = [t["id"] for t in sels]
        if not messagebox.askyesno("Hard Delete", f"Permanently delete {len(ids)} task(s)? This cannot be undone."):
            return
        logger.debug("HARD delete ids: %s", ids)
        # remove from DB
        self.db["tasks"] = [t for t in self.db["tasks"] if t["id"] not in ids]
        save_db(self.db)
        self.refresh()

    # ===== Bulk helpers =====
    def set_priority_bulk(self, code: str):
        changed = False
        for t in self.selected_tasks():
            t["priority"] = code
            if code == "D" and t.get("repeat", "none") == "none":
                t["repeat"] = "daily"
            changed = True
        if changed:
            save_db(self.db)
            self.refresh()

    def set_repeat_bulk(self, rep: str):
        target_rep = rep
        if rep == "custom":
            days = self._prompt_custom_repeat_days()
            if days is None:
                return
            target_rep = f"custom:{days}"
        changed = False
        for t in self.selected_tasks():
            t["repeat"] = target_rep
            changed = True
        if changed:
            save_db(self.db)
            self.refresh()

    def set_group_bulk(self, clear: bool = False):
        if clear:
            changed = False
            for t in self.selected_tasks():
                if t.get("group"):
                    t["group"] = ""
                    changed = True
            if changed:
                save_db(self.db)
                self.refresh()
            return

        # Collect existing groups
        groups = sorted({(t.get("group") or "").strip() for t in self.db["tasks"] if (t.get("group") or "").strip()})

        # Small Toplevel with autocomplete entry
        win = tk.Toplevel(self)
        win.title("Set Group")
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Group name:").grid(row=0, column=0, sticky="w")
        gvar = tk.StringVar()

        def cand():
            return groups

        entry = AutoCompleteEntry(frm, cand, textvariable=gvar, width=28)
        entry.grid(row=0, column=1, sticky="w", padx=6)

        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=2, pady=(10, 0), sticky="e")

        def _ok():
            g = gvar.get().strip()
            if g == "":
                win.destroy()
                return
            changed = False
            for t in self.selected_tasks():
                if t.get("group", "") != g:
                    t["group"] = g
                    changed = True
            if changed:
                save_db(self.db)
                self.refresh()
            win.destroy()

        ttk.Button(btns, text="OK", command=_ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=6)

        entry.focus_set()
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        width = win.winfo_width()
        height = win.winfo_height()
        x = max(0, min(self.winfo_pointerx() - width // 2, screen_w - width))
        y = max(0, min(self.winfo_pointery() - height // 2, screen_h - height))
        win.geometry(f"+{x}+{y}")
        self.wait_window(win)

    def set_due_bulk(self):
        s = simpledialog.askstring(
            "Set Due",
            "Enter due (YYYY-MM-DD [HH:MM], MM/DD [HH:MM], HH:MM, HHMM, or +2d +5h; 'midnight' ok):",
            parent=self
        )
        if s is None:
            return
        parsed = parse_due_entry(s.strip())
        if parsed is None:
            messagebox.showerror("Date error", "Invalid due format.")
            return
        val = fmt_due_for_store(parsed)
        changed = False
        for t in self.selected_tasks():
            t["due"] = val
            changed = True
        if changed:
            save_db(self.db)
            self.refresh()

    # ===== Bump =====
    def bump_days(self, n: int):
        for t in self.selected_tasks():
            dt = parse_stored_due(t.get("due", "")) or datetime.now()
            if len(t.get("due", "")) == 10:
                t["due"] = (dt.date() + timedelta(days=n)).strftime("%Y-%m-%d")
            else:
                t["due"] = (dt + timedelta(days=n)).strftime("%Y-%m-%d %H:%M")
            t["bumped_count"] = t.get("bumped_count", 0) + 1
        save_db(self.db)
        self.refresh()

    def bump_weeks(self, n: int):
        # NOTE: must call THROUGH self.
        self.bump_days(7 * n)

    def bump_months(self, n: int):
        for t in self.selected_tasks():
            dt = parse_stored_due(t.get("due", "")) or datetime.now()
            if len(t.get("due", "")) == 10:
                nd = add_months_dateonly(dt.date())
                t["due"] = nd.strftime("%Y-%m-%d")
            else:
                # keep simple 30-day month bump for time-of-day tasks
                t["due"] = (dt + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
            t["bumped_count"] = t.get("bumped_count", 0) + 1
        save_db(self.db)
        self.refresh()
