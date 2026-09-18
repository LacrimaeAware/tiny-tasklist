"""Recurrence advancement for repeating tasks (the 'midnight reset' logic).

Pure functions with no Tkinter dependency. `app.py` keeps the Tk timer
(`self.after`) and calls `advance_repeating_tasks` at startup and each midnight.
"""
from datetime import datetime, date
from typing import Optional

from .dates import parse_stored_due, next_due


def apply_skip_escalation(task: dict) -> None:
    """Bump a repeating task's priority for one missed occurrence.

    Saves the original priority to ``base_priority`` so it can be restored when the
    task is finally completed (or escalation is reset).
    """
    task["skip_count"] = int(task.get("skip_count", 0)) + 1
    if task["skip_count"] >= 2 and "base_priority" not in task:
        task["base_priority"] = task.get("priority", "M")
    if task["skip_count"] >= 3:
        task["priority"] = "U"
    elif task["skip_count"] >= 2:
        task["priority"] = "H"


def advance_repeating_tasks(db: dict, today: Optional[date] = None, hazard_enabled: bool = False) -> bool:
    """Advance repeating tasks to their next occurrence after *today*.

    Catches up multiple missed occurrences, applies skip escalation when enabled,
    and re-activates a previously completed task whose new due lands on today.
    Mutates ``db['tasks']`` in place. Returns True if anything changed.
    """
    today = today or date.today()
    changed = False

    for t in db.get("tasks", []):
        rep = t.get("repeat", "none")
        if rep in ("", "none", None):
            continue

        stored = t.get("due", "")
        due_dt = parse_stored_due(stored)
        if not due_dt:
            due_dt = datetime.combine(today, datetime.min.time())
            stored = due_dt.strftime("%Y-%m-%d")

        had_time = isinstance(stored, str) and len(stored) > 10
        original_time = due_dt.time()

        # Advance while the next theoretical occurrence is already <= today.
        while True:
            next_day = next_due(due_dt.date(), rep)
            # Stop on no forward progress (malformed repeat) to avoid an infinite loop.
            if next_day is None or next_day <= due_dt.date() or next_day > today:
                break
            due_dt = datetime.combine(next_day, original_time if had_time else datetime.min.time())
            changed = True
            if hazard_enabled:
                apply_skip_escalation(t)

        # Re-activate a completed task whose (possibly advanced) due is today.
        if t.get("completed_at") and due_dt.date() == today:
            t["completed_at"] = ""
            changed = True

        t["due"] = due_dt.strftime("%Y-%m-%d %H:%M") if had_time else due_dt.strftime("%Y-%m-%d")

    return changed
