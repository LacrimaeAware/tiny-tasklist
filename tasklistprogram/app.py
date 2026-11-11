import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Optional, Tuple, List
from datetime import datetime, date, timedelta

from .core.dates import parse_due_flexible, parse_due_entry, fmt_due_for_store
from .core.model import load_db, save_db, get_task, delete_task, stats_summary, normalize_settings, current_rev
from .core import filters, scheduler
from .ui.dialogs import (
    EditDialog,
    StatsDialog,
    SettingsDialog,
    RemindersDialog,
    PasteImportDialog,
    HelpDialog,
    MantraDialog,
    JournalDialog,
)
from .core.io_import import import_from_string
from .core.documents import (
    sync_task_notes,
    move_task_document_if_needed,
    open_document,
    append_journal_manual,
    ensure_journal_path,
    open_directory,
    get_mantras_file_path,
    read_task_notes_from_file,
    task_doc_path,
    pick_mantra_of_day,
    pick_random_mantra,
    DATA_DIR,
)

from .core.actions import ActionsMixin

from .ui.listview import TaskListView
from .ui.controls import AutoCompleteEntry
from .ui import theme
from .core.constants import PRIO_ICON

logger = logging.getLogger(__name__)

class TaskApp(ActionsMixin, tk.Tk):
    REPEAT_OPTIONS = ["none", "daily", "weekdays", "weekly", "bi-weekly", "monthly", "custom"]

    def __init__(self):
        super().__init__()
        self.title("Tiny Tasklist")
        self.geometry("1120x660")
        self._set_app_icon()
        self.db = load_db()

        # Theming: remember the native ttk theme + default bg so light mode can
        # restore them, then apply the saved theme at the end of __init__.
        self.style = ttk.Style(self)
        self._native_theme = self.style.theme_use()
        self._default_bg = self.cget("bg")
        self._theme_mode = "light"

        # Track last shown mantra to avoid consecutive duplicates
        self.last_shown_mantra = None

        # Expanded/collapsed state by group name
        self.group_state = {}  # {group_name: True/False}

        # Menu bar
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings...", command=self.open_settings)
        file_menu.add_command(label="Reminders…", command=self.open_reminders)
        file_menu.add_command(label="Import Tasks…", command=self.import_tasks)
        file_menu.add_command(label="Import (paste text)…", command=self.import_tasks_paste)
        file_menu.add_separator()
        file_menu.add_command(label="Open Data Folder", command=self.open_repository_folder)
        menubar.add_cascade(label="File", menu=file_menu)

        mantra_menu = tk.Menu(menubar, tearoff=0)
        mantra_menu.add_command(label="Show Mantra…", command=self.open_mantras)
        mantra_menu.add_command(label="Open Mantra File", command=self.open_mantra_file)
        menubar.add_cascade(label="Mantras", menu=mantra_menu)

        journal_menu = tk.Menu(menubar, tearoff=0)
        journal_menu.add_command(label="Journal…", command=self.open_journal)
        journal_menu.add_command(label="Open Today's Journal", command=self.open_today_journal)
        menubar.add_cascade(label="Journal", menu=journal_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Dark Mode", command=self.toggle_theme)
        view_menu.add_separator()
        view_menu.add_command(label="Open Web App in Browser", command=self.open_web_app)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help / Guide…", command=self.open_help)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.menubar = menubar
        self.config(menu=menubar)

        self.sort_state: Tuple[str, bool] = ("due", True)  # (column, ascending)

        # Top controls
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Title:").pack(side=tk.LEFT)
        self.title_var = tk.StringVar()
        title_entry = AutoCompleteEntry(top, self._title_candidates, textvariable=self.title_var, width=34)
        title_entry.pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="Due:").pack(side=tk.LEFT, padx=(8,0))
        self.due_var = tk.StringVar()
        due_entry = ttk.Entry(top, textvariable=self.due_var, width=22)
        due_entry.pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="Priority:").pack(side=tk.LEFT, padx=(8,0))
        self.priority_var = tk.StringVar(value="M")
        prio_combo = ttk.Combobox(top, textvariable=self.priority_var, width=6,
                                  values=["H","M","L","D","Misc"], state="readonly")
        prio_combo.pack(side=tk.LEFT, padx=4)
        prio_combo.bind("<<ComboboxSelected>>", self._maybe_autoset_repeat)

        ttk.Label(top, text="Repeat:").pack(side=tk.LEFT, padx=(8,0))
        self.repeat_var = tk.StringVar(value="none")
        repeat_combo = ttk.Combobox(top, textvariable=self.repeat_var, width=10,
                                    values=self.REPEAT_OPTIONS, state="readonly")
        repeat_combo.pack(side=tk.LEFT, padx=4)
        repeat_combo.bind("<<ComboboxSelected>>", self._on_repeat_selected)
        self.repeat_combo = repeat_combo

        self.notes_txt = tk.Text(top, width=32, height=2, wrap="word")
        self.notes_txt.pack(side=tk.LEFT, padx=(8, 4))
        self.notes_txt.bind("<Return>", lambda e: (self.add_task(), "break"))
        self.notes_txt.bind("<Shift-Return>", lambda e: None)

        ttk.Button(top, text="Add", command=self.add_task).pack(side=tk.LEFT)
        ttk.Button(top, text="Stats", command=self.open_stats).pack(side=tk.LEFT, padx=(8,0))

        # Keyboard flow
        title_entry.bind("<Shift-Return>", self.quick_add_default)

        # Filter/Search row
        filt = ttk.Frame(self, padding=(8,0,8,8))
        filt.pack(fill=tk.X)
        settings = normalize_settings(self.db.get("settings", {}))
        self.db["settings"] = settings

        ttk.Button(filt, text="★ Today", command=self.show_today).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(filt, text="Category:").pack(side=tk.LEFT)
        category_default = settings.get("ui_category_scope", "active")
        if category_default not in ["active", "repeating", "overdue", "done", "deleted", "suspended", "all"]:
            category_default = "active"
        self.category_filter_var = tk.StringVar(value=category_default)
        category_combo = ttk.Combobox(
            filt,
            textvariable=self.category_filter_var,
            width=10,
            values=["active", "repeating", "overdue", "done", "deleted", "suspended", "all"],
            state="readonly",
        )
        category_combo.pack(side=tk.LEFT, padx=6)

        ttk.Label(filt, text="Time:").pack(side=tk.LEFT, padx=(8, 0))
        time_default = settings.get("ui_time_scope", "today")
        if time_default not in ["any", "today", "week", "month", "custom"]:
            time_default = "today"
        self.time_filter_var = tk.StringVar(value=time_default)
        time_combo = ttk.Combobox(
            filt,
            textvariable=self.time_filter_var,
            width=9,
            values=["any", "today", "week", "month", "custom"],
            state="readonly",
        )
        time_combo.pack(side=tk.LEFT, padx=6)

        self.custom_time_date = settings.get("ui_time_custom_date", "")

        self.custom_date_btn = ttk.Button(filt, text="Pick date…", command=self.pick_custom_filter_date)

        def _apply_filters(*_):
            st = self.db.setdefault("settings", {})
            st["ui_category_scope"] = self.category_filter_var.get()
            st["ui_time_scope"] = self.time_filter_var.get()
            st["ui_time_custom_date"] = self.custom_time_date
            save_db(self.db)
            self._sync_custom_date_button()
            self.refresh()

        category_combo.bind("<<ComboboxSelected>>", _apply_filters)
        time_combo.bind("<<ComboboxSelected>>", _apply_filters)

        self.search_label = ttk.Label(filt, text="Search:")
        self.search_label.pack(side=tk.LEFT, padx=(16,0))
        self._sync_custom_date_button()
        self.search_var = tk.StringVar()
        s_entry = ttk.Entry(filt, textvariable=self.search_var, width=34)
        s_entry.pack(side=tk.LEFT, padx=6)
        self.search_var.trace_add("write", lambda *args: self.refresh())

        ttk.Label(filt, text="Min prio:").pack(side=tk.LEFT, padx=(16, 0))
        self.minprio_ui = tk.StringVar(value=self.db.get("settings", {}).get("min_priority_visible", "L"))
        mincombo = ttk.Combobox(filt, textvariable=self.minprio_ui, width=8,
                                values=["H", "M", "L", "D", "Misc"], state="readonly")
        mincombo.pack(side=tk.LEFT, padx=6)
        def _apply_minprio(*_):
            s = self.db.setdefault("settings", {})
            s["min_priority_visible"] = self.minprio_ui.get()
            save_db(self.db)
            self.refresh()
        mincombo.bind("<<ComboboxSelected>>", _apply_minprio)

        # Grouping toggle
        self.group_view = tk.BooleanVar(value=bool(settings.get("ui_group_view", False)))

        def _apply_group_view():
            s = self.db.setdefault("settings", {})
            s["ui_group_view"] = bool(self.group_view.get())
            save_db(self.db)
            self.refresh()

        ttk.Checkbutton(filt, text="Group view", variable=self.group_view, command=_apply_group_view) \
            .pack(side=tk.LEFT, padx=(16, 0))

        # --- style: make the caret button flat and remove focus ring.
        # (Table/selection styling is handled by theme.apply_theme.)
        style = self.style
        style.configure("Caret.TButton", padding=(4, 1), relief="flat")
        style.map("Caret.TButton",
                  relief=[("pressed", "sunken"), ("!pressed", "flat")],
                  focuscolor=[("!disabled", self.cget("background"))],
                  highlightthickness=[("!disabled", 0)],
                  borderwidth=[("!disabled", 0)])

        # Single caret toggle: ▼ = default expanded, ▶ = default collapsed
        self.group_toggle_var = tk.StringVar(value="▼")
        ttk.Button(
            filt,
            textvariable=self.group_toggle_var,
            width=2,
            command=self._toggle_all_groups,
            style="Caret.TButton"
        ).pack(side=tk.LEFT, padx=(6, 10))

        self.mark_done_btn = ttk.Button(filt, text="Mark Done", command=self.mark_done)
        self.delete_btn = ttk.Button(filt, text="Delete", command=self.soft_delete)
        self.suspend_btn = ttk.Button(filt, text="Suspend", command=self.suspend_tasks)
        self.mark_done_btn.pack(side=tk.LEFT, padx=(16, 4))
        self.delete_btn.pack(side=tk.LEFT, padx=4)
        self.suspend_btn.pack(side=tk.LEFT, padx=4)

        # Status bar (docked at the bottom; created before the list so it reserves space).
        status = ttk.Frame(self, padding=(10, 3))
        status.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Separator(self, orient="horizontal").pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(status, textvariable=self.status_var, foreground="#555")
        self.status_label.pack(side=tk.LEFT)

        # Task table
        initial_palette = theme.get_palette(self.db.get("settings", {}).get("ui_theme", "light"))
        self.list = TaskListView(self, on_request_edit=self.edit_task,
                                 request_refresh=self.refresh, palette=initial_palette)

        # Keep header sort behavior in app.py so sort state stays consistent
        def _header_sort(col):
            self.sort_by(col)
        for c in ("id","due","rem","prio","rep","title","notes","times"):
            header_text = self.list.tree.heading(c, "text")
            self.list.tree.heading(c, text=header_text, command=lambda col=c: _header_sort(col))

        # Right-click context menu
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Edit", command=self.edit_task)
        self.menu.add_command(label="Delete (soft)", command=self.soft_delete)
        self.menu.add_command(label="Restore", command=self.restore)
        self.menu.add_command(label="Hard Delete…", command=self.hard_delete)
        self.menu.add_command(label="Suspend", command=self.suspend_tasks)
        self.menu.add_command(label="Unsuspend", command=self.unsuspend_tasks)
        self.menu.add_command(label="Open Document…", command=self.open_task_document)

        setp = tk.Menu(self.menu, tearoff=0)
        setp.add_command(label="High",   command=lambda: self.set_priority_bulk("H"))
        setp.add_command(label="Medium", command=lambda: self.set_priority_bulk("M"))
        setp.add_command(label="Low",    command=lambda: self.set_priority_bulk("L"))
        setp.add_command(label="Daily",  command=lambda: self.set_priority_bulk("D"))
        setp.add_command(label="Misc",   command=lambda: self.set_priority_bulk("X"))
        self.menu.add_cascade(label="Set Priority", menu=setp)

        setr = tk.Menu(self.menu, tearoff=0)
        for rlab, rval in [("none","none"),("daily","daily"),("weekdays","weekdays"),("weekly","weekly"),("bi-weekly","bi-weekly"),("monthly","monthly"),("custom…","custom")]:
            setr.add_command(label=rlab, command=lambda v=rval: self.set_repeat_bulk(v))
        self.menu.add_cascade(label="Set Repeat", menu=setr)

        self.menu.add_command(label="Set Due…", command=self.set_due_bulk)

        # Bulk set/clear group
        self.menu.add_command(label="Set Group…", command=self.set_group_bulk)
        self.menu.add_command(label="Clear Group", command=lambda: self.set_group_bulk(clear=True))

        # Attach context menu to the task table
        self.list.tree.bind("<Button-3>", self.popup_menu)
        self.list.tree.bind("<<TreeviewSelect>>", lambda e: self._update_action_buttons())

        # Apply the saved theme now that all widgets exist.
        self._apply_theme(self.db.get("settings", {}).get("ui_theme", "light"))

        # Initial refresh & schedule resets
        self.refresh()
        self.reset_repeating_tasks(catchup=True)
        self.schedule_midnight_reset()
        self.after(600, self._maybe_show_mantra_on_launch)

        # Keyboard shortcuts
        self.bind("<Delete>", lambda e: self.soft_delete())
        self.bind("<Control-Return>", lambda e: self.mark_done())

        # Pick up external edits (e.g. from the web app) when the window regains focus.
        self.bind("<FocusIn>", self._on_focus_in)

    def _reload_if_changed(self) -> bool:
        """Reload from the store when another process (the web server) saved since our last read.

        Returns True when a reload happened. Errors are swallowed: a failed check must
        not break the UI, and the next focus or timer tick retries.
        """
        try:
            rev = current_rev()
            if rev is not None and rev != self.db.get("_rev"):
                self.db = load_db()
                return True
        except Exception:
            logger.debug("store revision check failed", exc_info=True)
        return False

    def _on_focus_in(self, event=None):
        """Reload if the store changed externally since our last read (web edits)."""
        if event is not None and event.widget is not self:
            return  # ignore focus events from child widgets
        if self._reload_if_changed():
            self.refresh()
    # ===== Repeat resets =====
    def schedule_midnight_reset(self):
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        delay_ms = max(1000, int((tomorrow - now).total_seconds() * 1000))
        self.after(delay_ms, lambda: self.reset_repeating_tasks(catchup=False))

    def reset_repeating_tasks(self, catchup: bool):
        """Advance repeating tasks whose next occurrence is already due (launch catch-up, midnight reset).

        The midnight run fires from a timer, possibly hours after the window last had
        focus, so reload first when the store moved on: saving the stale in-memory copy
        would overwrite edits made in the browser in the meantime.
        """
        self._reload_if_changed()
        changed = scheduler.advance_repeating_tasks(
            self.db, today=date.today(), hazard_enabled=self._hazard_enabled()
        )
        if changed:
            save_db(self.db)
            self.refresh()

        # Schedule the next midnight run.
        if not catchup:
            self.schedule_midnight_reset()

    # ===== Helpers =====
    def _toggle_all_groups(self):
        # Toggle global default expansion in the list view and refresh.
        if self.list.is_default_expanded():
            self.list.collapse_all()
            self.group_toggle_var.set("▶")
        else:
            self.list.expand_all()
            self.group_toggle_var.set("▼")
        self.refresh()

    def _maybe_autoset_repeat(self, event=None):
        raw = self.priority_var.get()
        if raw.lower() == 'misc':
            return
        if str(raw).upper() == "D":
            self.repeat_var.set("daily")

    def _on_repeat_selected(self, event=None):
        selected = (self.repeat_var.get() or "none").strip().lower()
        if selected != "custom":
            return
        custom_value = self._prompt_custom_repeat_days()
        if custom_value is None:
            self.repeat_var.set("none")
            return
        self.repeat_var.set(f"custom:{custom_value}")

    def _prompt_custom_repeat_days(self):
        return simpledialog.askinteger(
            "Custom Repeat",
            "Repeat every how many days?\n\nExample: 6 means repeats every 6 days.",
            parent=self,
            minvalue=1,
        )

    def _hazard_enabled(self) -> bool:
        return bool(self.db.get("settings", {}).get("hazard_escalation_enabled", False))

    def reset_hazard_escalation(self):
        changed = False
        for t in self.db.get("tasks", []):
            if int(t.get("skip_count", 0)) != 0:
                t["skip_count"] = 0
                changed = True
            if "base_priority" in t:
                t["priority"] = t.get("base_priority", t.get("priority", "M"))
                t.pop("base_priority", None)
                changed = True
        if changed:
            save_db(self.db)
            self.refresh()
        messagebox.showinfo("Hazard Escalation", "Hazard escalation has been reset for all tasks.")

    # ===== Window chrome =====
    def _set_app_icon(self):
        """Set the window/taskbar icon (best-effort; never fatal)."""
        try:
            icon_path = Path(__file__).resolve().parent / "ui" / "assets" / "icon.png"
            if icon_path.exists():
                self._icon_img = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass
        if sys.platform.startswith("win"):
            # Make Windows use the window icon in the taskbar instead of python's.
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TinyTasklist.App")
            except Exception:
                pass

    def open_web_app(self):
        """Open the web version in the browser, starting the local server if needed.

        The web app and this desktop app are two front-ends over the same SQLite store;
        this just launches the local server (if it isn't already running) and opens it.
        """
        import socket
        import webbrowser
        import subprocess
        port = 8000

        def _running():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except OSError:
                return False
            finally:
                s.close()

        if _running():
            webbrowser.open(f"http://localhost:{port}")
            return

        try:
            exe = sys.executable or "python"
            pyw = exe.replace("python.exe", "pythonw.exe")
            if Path(pyw).exists():
                exe = pyw
            root = Path(__file__).resolve().parent.parent
            flags = subprocess.DETACHED_PROCESS if sys.platform.startswith("win") else 0
            subprocess.Popen(
                [exe, "-m", "tasklistprogram.webserver", "--port", str(port)],
                cwd=str(root), creationflags=flags, close_fds=True,
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Web App", f"Could not start the web server:\n{e}")
            return
        # Give the server a moment to bind, then open the browser.
        self.after(900, lambda: webbrowser.open(f"http://localhost:{port}"))

    # ===== Theming =====
    def _apply_theme(self, mode: str):
        mode = mode if mode in ("light", "dark") else "light"
        pal = theme.get_palette(mode)
        theme.apply_theme(self, self.style, pal, self._native_theme)

        # Root window + classic (non-ttk) widgets the theme can't reach via styles.
        self.configure(bg=(pal["window_bg"] if mode == "dark" else self._default_bg))
        if hasattr(self, "list"):
            self.list.apply_palette(pal)
        if hasattr(self, "status_label"):
            self.status_label.configure(foreground=pal["status_fg"])
        if hasattr(self, "notes_txt"):
            self.notes_txt.configure(
                background=pal["field_bg"] if mode == "dark" else "white",
                foreground=pal["entry_fg"] if mode == "dark" else "black",
                insertbackground=pal["entry_fg"] if mode == "dark" else "black",
            )
        self._theme_mode = mode

    def toggle_theme(self):
        new_mode = "light" if self._theme_mode == "dark" else "dark"
        self.db.setdefault("settings", {})["ui_theme"] = new_mode
        save_db(self.db)
        self._apply_theme(new_mode)
        self.refresh()

    def _display_title(self, task: dict) -> str:
        title = task.get("title", "")
        if self._hazard_enabled() and int(task.get("skip_count", 0)) >= 1:
            return f"⚠ {title}"
        return title

    def _title_candidates(self):
        items = [(t.get("title",""), t.get("times_completed",0)) for t in self.db["tasks"] if t.get("title")]
        items.sort(key=lambda x: (-x[1], x[0].lower()))
        seen, out = set(), []
        for title, _ in items:
            if title not in seen:
                seen.add(title); out.append(title)
        return out

    def selected_tasks(self) -> List[dict]:
        ids = self.list.selected_task_ids()
        return [get_task(self.db, tid) for tid in ids if get_task(self.db, tid)]

    def popup_menu(self, event):
        tree = self.list.tree
        iid = tree.identify_row(event.y)
        kind = self.list.identify_row_kind(iid)

        if not iid or kind != "task":
            return  # only allow popup on real task rows

        # If the clicked row isn't already in the selection, select JUST that row.
        # If it IS already selected, keep the existing multi-selection intact.
        current = set(tree.selection())
        if iid not in current:
            tree.selection_set(iid)

        self._configure_context_menu()
        self.menu.tk_popup(event.x_root, event.y_root)

    def _configure_context_menu(self):
        self.menu.delete(0, tk.END)
        
        # Create Edit cascade submenu
        edit_menu = tk.Menu(self.menu, tearoff=0)
        edit_menu.add_command(label="Manual Edit", command=self.edit_task)
        
        # Set Priority cascade
        priority_menu = tk.Menu(edit_menu, tearoff=0)
        priority_menu.add_command(label="High", command=lambda: self.set_priority_bulk("H"))
        priority_menu.add_command(label="Medium", command=lambda: self.set_priority_bulk("M"))
        priority_menu.add_command(label="Low", command=lambda: self.set_priority_bulk("L"))
        priority_menu.add_command(label="Daily", command=lambda: self.set_priority_bulk("D"))
        priority_menu.add_command(label="Misc", command=lambda: self.set_priority_bulk("X"))
        edit_menu.add_cascade(label="Set Priority", menu=priority_menu)
        
        # Set Repeat cascade
        repeat_menu = tk.Menu(edit_menu, tearoff=0)
        repeat_menu.add_command(label="none", command=lambda: self.set_repeat_bulk("none"))
        repeat_menu.add_command(label="daily", command=lambda: self.set_repeat_bulk("daily"))
        repeat_menu.add_command(label="weekdays", command=lambda: self.set_repeat_bulk("weekdays"))
        repeat_menu.add_command(label="weekly", command=lambda: self.set_repeat_bulk("weekly"))
        repeat_menu.add_command(label="bi-weekly", command=lambda: self.set_repeat_bulk("bi-weekly"))
        repeat_menu.add_command(label="monthly", command=lambda: self.set_repeat_bulk("monthly"))
        repeat_menu.add_command(label="custom…", command=lambda: self.set_repeat_bulk("custom"))
        edit_menu.add_cascade(label="Set Repeat", menu=repeat_menu)
        
        edit_menu.add_command(label="Set Due…", command=self.set_due_bulk)
        edit_menu.add_command(label="Set Group…", command=self.set_group_bulk)
        
        # Bump cascade
        bump_menu = tk.Menu(edit_menu, tearoff=0)
        bump_menu.add_command(label="+1 day", command=lambda: self.bump_days(1))
        bump_menu.add_command(label="-1 day", command=lambda: self.bump_days(-1))
        bump_menu.add_command(label="+1 week", command=lambda: self.bump_weeks(1))
        bump_menu.add_command(label="-1 week", command=lambda: self.bump_weeks(-1))
        edit_menu.add_cascade(label="Bump", menu=bump_menu)
        
        self.menu.add_cascade(label="Edit", menu=edit_menu)
        
        # State-aware Delete/Restore and Suspend/Unsuspend
        selection = self.selected_tasks()
        show_restore = any(t.get("is_deleted") for t in selection)
        show_delete = any(not t.get("is_deleted") for t in selection)
        show_unsuspend = any(t.get("is_suspended") for t in selection)
        show_suspend = any(not t.get("is_suspended") for t in selection)
        delete_label = "Restore" if show_restore and not show_delete else "Delete (soft)"
        delete_cmd = self.restore if delete_label == "Restore" else self.soft_delete
        suspend_label = "Unsuspend" if show_unsuspend and not show_suspend else "Suspend"
        suspend_cmd = self.unsuspend_tasks if suspend_label == "Unsuspend" else self.suspend_tasks
        self.menu.add_command(label=delete_label, command=delete_cmd)
        self.menu.add_command(label="Hard Delete…", command=self.hard_delete)
        self.menu.add_command(label=suspend_label, command=suspend_cmd)
        self.menu.add_command(label="Open Document…", command=self.open_task_document)

    def _update_action_buttons(self):
        if not hasattr(self, "list"):
            return
        selection = self.selected_tasks()
        has_deleted = any(t.get("is_deleted") for t in selection)
        has_active = any(not t.get("is_deleted") for t in selection)
        has_suspended = any(t.get("is_suspended") for t in selection)
        has_unsuspended = any(not t.get("is_suspended") for t in selection)
        if has_deleted and not has_active:
            self.delete_btn.config(text="Restore", command=self.restore, state="normal")
        else:
            self.delete_btn.config(text="Delete", command=self.soft_delete, state="normal" if selection else "disabled")
        if has_suspended and not has_unsuspended:
            self.suspend_btn.config(text="Unsuspend", command=self.unsuspend_tasks, state="normal")
        else:
            self.suspend_btn.config(text="Suspend", command=self.suspend_tasks, state="normal" if selection else "disabled")

    def open_task_document(self):
        sels = self.selected_tasks()
        if not sels:
            return
        task = sels[0]
        move_task_document_if_needed(task)
        # Read external changes before opening
        if read_task_notes_from_file(task):
            # Save DB only if external changes were detected and applied
            save_db(self.db)
        else:
            # No external changes, ensure file is synced with current notes
            # (save_db not needed here as sync_task_notes doesn't modify task)
            sync_task_notes(task)
        open_document(task_doc_path(task))

    # ===== Add & Quick Add =====
    def add_task(self):
        title = self.title_var.get().strip()
        if not title: return
        due_s = self.due_var.get().strip()

        parsed = parse_due_entry(due_s) if due_s else None
        if due_s and parsed is None:
            messagebox.showerror("Date error",
                "Due must be 'YYYY-MM-DD [HH:MM]', 'MM/DD [HH:MM]', 'HH:MM', 'HHMM', or relative like '+2d +5h' (use 'midnight' for 23:59).")
            return
        rawp = self.priority_var.get()
        prio = ("X" if str(rawp).lower()=="misc" else str(rawp).upper())
        rep = self.repeat_var.get()
        notes = self.notes_txt.get("1.0", "end-1c").strip()
        if prio == "D": rep = "daily"
        t = {
            "id": self.db["next_id"],
            "title": title,
            "notes": notes,
            "priority": prio if prio in ("H","M","L","D","X") else "M",
            "due": fmt_due_for_store(parsed) if due_s else "",
            "repeat": rep,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "completed_at": "",
            "times_completed": 0,
            "history": [],
            "is_deleted": False,
            "is_suspended": False,
            "skip_count": 0,
            "group": ""  # group set via Edit or bulk action
        }
        self.db["tasks"].append(t)
        self.db["next_id"] += 1
        save_db(self.db)
        sync_task_notes(t)
        save_db(self.db)
        self.title_var.set("")
        self.due_var.set("")
        self.notes_txt.delete("1.0", "end")
        self.refresh(select_id=t["id"])

    def quick_add_default(self, event=None):
        title = self.title_var.get().strip()
        if not title: return "break"
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        t = {
            "id": self.db["next_id"],
            "title": title,
            "notes": "",
            "priority": "M",
            "due": tomorrow,
            "repeat": "none",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "completed_at": "",
            "times_completed": 0,
            "history": [],
            "is_deleted": False,
            "is_suspended": False,
            "skip_count": 0,
            "group": ""
        }
        self.db["tasks"].append(t); self.db["next_id"] += 1
        save_db(self.db)
        sync_task_notes(t)
        save_db(self.db)
        self.title_var.set("")
        self.refresh(select_id=t["id"])
        return "break"

    # ===== Edit / Done / Delete / Restore =====
    def edit_task(self):
        sels = self.selected_tasks()
        if not sels: return
        if len(sels) > 1:
            messagebox.showinfo("Edit", "Please select a single task to edit.")
            return
        t = sels[0]
        def on_save(data):
            t["title"] = data["title"]
            t["due"] = data["due"]
            t["priority"] = ("X" if str(data["priority"]).lower()=="misc" else data["priority"])
            t["repeat"] = data["repeat"]
            t["notes"] = data["notes"]
            t["group"] = data.get("group","").strip()
            t["updated_at"] = datetime.now().isoformat(timespec="seconds")
            move_task_document_if_needed(t)
            sync_task_notes(t)
            save_db(self.db)
            self.refresh(select_id=t["id"])
        EditDialog(self, t, on_save)

    # ===== Filter/Search/Sort/Refresh =====
    def passes_filter(self, t, category_scope: str, time_scope: str):
        return filters.passes_filter(
            t, self.db.get("settings", {}), category_scope, time_scope, self._custom_filter_date()
        )

    def _custom_filter_date(self):
        if not self.custom_time_date:
            return None
        parsed = parse_due_flexible(self.custom_time_date)
        if parsed is None:
            return None
        if isinstance(parsed, tuple):
            parsed = parsed[1]
        return parsed.date()

    def _sync_custom_date_button(self):
        if self.time_filter_var.get() == "custom":
            label = self.custom_time_date or "Pick date…"
            self.custom_date_btn.configure(text=label)
            self.custom_date_btn.pack(side=tk.LEFT, padx=(0, 6), before=self.search_label)
        else:
            self.custom_date_btn.pack_forget()

    def pick_custom_filter_date(self):
        initial = self.custom_time_date or date.today().isoformat()
        value = simpledialog.askstring(
            "Custom Time Filter",
            "Show tasks due on or before which date?\nUse YYYY-MM-DD (example: 2026-03-15).",
            parent=self,
            initialvalue=initial,
        )
        if value is None:
            return
        value = value.strip()
        parsed = parse_due_flexible(value)
        if parsed is None:
            messagebox.showerror("Custom Time Filter", "Invalid date. Use YYYY-MM-DD or another supported date format.")
            return
        if isinstance(parsed, tuple):
            parsed = parsed[1]
        self.custom_time_date = parsed.strftime("%Y-%m-%d")
        self.time_filter_var.set("custom")

        st = self.db.setdefault("settings", {})
        st["ui_time_scope"] = "custom"
        st["ui_time_custom_date"] = self.custom_time_date
        save_db(self.db)
        self._sync_custom_date_button()
        self.refresh()

    def show_today(self):
        """Jump back to the daily focus view: active tasks due today/overdue."""
        self.category_filter_var.set("active")
        self.time_filter_var.set("today")
        self.search_var.set("")
        st = self.db.setdefault("settings", {})
        st["ui_category_scope"] = "active"
        st["ui_time_scope"] = "today"
        save_db(self.db)
        self._sync_custom_date_button()
        self.refresh()

    def sort_by(self, col: str):
        current_col, ascending = self.sort_state
        ascending = not ascending if current_col == col else True
        self.sort_state = (col, ascending)
        self.refresh()

    def refresh(self, select_id: Optional[int] = None):
        category_scope = self.category_filter_var.get()
        time_scope = self.time_filter_var.get()
        query = self.search_var.get().strip()
        col, asc = self.sort_state

        tasks = [
            t for t in self.db["tasks"]
            if self.passes_filter(t, category_scope, time_scope) and filters.search_match(t, query)
        ]
        tasks.sort(key=lambda x: filters.sort_key_for(x, col), reverse=not asc)
        for t in tasks:
            t["_display_title"] = self._display_title(t)

        grouped = bool(self.group_view.get())

        self.list.render(
            tasks,
            scope=category_scope,
            prio_icon=PRIO_ICON,
            reminder_chip_fn=self._reminder_chip,
            grouped=grouped,
        )

        if select_id is not None:
            id_idx = self.list.COLS.index("id")
            for iid in self.list.tree.get_children():
                vals = self.list.tree.item(iid)["values"]
                if not vals or len(vals) <= id_idx:
                    continue
                try:
                    row_id = int(vals[id_idx])
                except Exception:
                    continue
                if str(row_id) == str(select_id):
                    self.list.tree.selection_set(iid)
                    self.list.tree.see(iid)
                    break
        self._apply_sort_indicators(category_scope)
        self._update_status(len(tasks))
        self._update_action_buttons()

    def _apply_sort_indicators(self, scope: str):
        """Show ▲/▼ on the active sort column header so the current sort is visible."""
        col, asc = self.sort_state
        arrow = " ▲" if asc else " ▼"
        for c in self.list.COLS:
            base = "DELETED" if (c == "due" and scope == "deleted") else self.list.HEADERS[c]
            self.list.tree.heading(c, text=base + (arrow if c == col else ""))

    def _update_status(self, shown: int):
        if not hasattr(self, "status_var"):
            return
        summary = stats_summary(self.db)
        open_count = summary["open"]
        done_today = summary["done_today"]
        self.status_var.set(f"Showing {shown}   ·   Open {open_count}   ·   Done today {done_today}")

    # ===== Stats / Settings / Reminders =====
    def open_help(self, initial_tab: str = "tutorial"):
        HelpDialog(self, initial_tab=initial_tab)

    def open_mantras(self):
        def _next():
            # Reload mantras from file each time
            mantra = pick_random_mantra(self.last_shown_mantra)
            self.last_shown_mantra = mantra
            return mantra

        def _add():
            text = simpledialog.askstring("Add Mantra", "Enter a new mantra:", parent=self)
            if text:
                # Append to the mantra file
                path = get_mantras_file_path()
                current_content = path.read_text(encoding="utf-8")
                if not current_content.endswith('\n'):
                    current_content += '\n'
                path.write_text(current_content + text.strip() + '\n', encoding="utf-8")
                return text.strip()
            return None

        # Load mantras from file and pick initial one
        initial = pick_mantra_of_day()
        self.last_shown_mantra = initial
        # MantraDialog loads from file via callbacks
        MantraDialog(self, on_add=_add, on_next=_next, initial=initial)

    def _maybe_show_mantra_on_launch(self):
        settings = self.db.get("settings", {})
        if not settings.get("mantras_autoshow", True):
            return
        today_key = date.today().isoformat()
        if settings.get("last_mantra_date") == today_key:
            return
        settings["last_mantra_date"] = today_key
        save_db(self.db)
        self.open_mantras()

    def open_journal(self):
        def _add_entry(text: str):
            append_journal_manual(text)

        def _open_file():
            path = ensure_journal_path()
            open_document(path)

        JournalDialog(self, on_add_entry=_add_entry, on_open_file=_open_file)

    def open_today_journal(self):
        path = ensure_journal_path()
        open_document(path)
    
    def open_repository_folder(self):
        """Open the data directory in the system file explorer."""
        open_directory(DATA_DIR)
    
    def open_mantra_file(self):
        """Open the mantras file for manual editing."""
        path = get_mantras_file_path()
        open_document(path)

    def import_tasks_paste(self):
        def _do(text):
            added, failed, details = import_from_string(text, self.db, return_details=True)
            if added:
                save_db(self.db)
                self.refresh()
            return added, failed, details

        PasteImportDialog(self, on_import_text=_do)

    def open_stats(self):
        summary = stats_summary(self.db)
        StatsDialog(self, summary)

    def import_tasks(self):
        from .core.io_import import import_from_txt
        path = filedialog.askopenfilename(title="Import tasks",
                                          filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path: return
        try:
            added, failed, details = import_from_txt(path, self.db, return_details=True)
            if added:
                save_db(self.db)
                self.refresh()
            if failed:
                detail_preview = "\n".join(f"- {d}" for d in details[:8])
                extra = "" if len(details) <= 8 else f"\n...and {len(details)-8} more."
                messagebox.showwarning(
                    "Import",
                    f"Imported {added} task(s). Skipped {failed} line(s).\n\nReasons:\n{detail_preview}{extra}"
                )
                logger.debug("import skipped lines: %s", details)
            else:
                messagebox.showinfo("Import", f"Imported {added} task(s).")
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

    def open_settings(self):
        def on_save(s):
            merged = normalize_settings(self.db.get("settings", {}))
            reset_requested = bool(s.pop("reset_hazard_escalation", False))
            merged.update(s)
            self.db["settings"] = merged
            save_db(self.db)
            if reset_requested:
                self.reset_hazard_escalation()
        SettingsDialog(self, self.db.get("settings", None), on_save)

    def open_reminders(self):
        from .core.reminders import pending_reminders
        pending = pending_reminders(self.db)
        if not pending:
            messagebox.showinfo("Reminders", "No pending reminders right now.")
            return

        def on_ack(pairs):
            for tid, key in pairs:
                task = next((x for x in self.db["tasks"] if x["id"] == tid), None)
                if task:
                    acks = set(task.get("acknowledged_checkpoints", []))
                    acks.add(key)
                    task["acknowledged_checkpoints"] = sorted(acks)
            save_db(self.db)

        RemindersDialog(self, pending, on_ack)

    def _reminder_chip(self, t) -> str:
        from .core.reminders import reminder_chip
        return reminder_chip(t, self.db.get("settings", {}))

def main():
    app = TaskApp()
    app.mainloop()

if __name__ == "__main__":
    main()
