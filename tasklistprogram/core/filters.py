"""Pure predicates for filtering, searching, and sorting tasks.

These functions have no Tkinter dependency so they can be unit-tested headlessly.
`app.py` wires them to the UI state (current scopes, search box, sort column).
"""
from datetime import datetime, date, timedelta
from typing import Optional

from .dates import parse_stored_due
from .constants import PRIORITY_ORDER, priority_rank

CATEGORY_SCOPES = ["active", "repeating", "overdue", "done", "deleted", "suspended", "all"]
TIME_SCOPES = ["any", "today", "week", "month", "custom"]


def priority_visible(task: dict, settings: dict) -> bool:
    """True if the task's priority is at or above the 'min priority to show' setting."""
    minv = (settings or {}).get("min_priority_visible", "L")
    return priority_rank(task.get("priority", "M")) >= priority_rank(minv)


def passes_category_filter(task: dict, category_scope: str) -> bool:
    done = bool(task.get("completed_at"))
    deleted = bool(task.get("is_deleted", False))
    suspended = bool(task.get("is_suspended", False))
    repeating = (task.get("repeat") or "").lower() not in ("", "none")

    if category_scope == "deleted":
        return deleted
    if category_scope == "suspended":
        return suspended and not deleted
    if category_scope == "done":
        return done and not deleted and not suspended

    if deleted or suspended or done:
        return False

    if category_scope == "overdue":
        d = parse_stored_due(task.get("due", "")) if task.get("due") else None
        return bool(d and d < datetime.now())
    if category_scope == "repeating":
        return repeating
    # "active", "all", or anything unknown -> visible
    return True


def passes_time_filter(
    task: dict,
    category_scope: str,
    time_scope: str,
    custom_date: Optional[date] = None,
    now: Optional[datetime] = None,
) -> bool:
    # Archived/status views are category-first and ignore time slicing.
    if category_scope in ("deleted", "suspended", "done"):
        return True

    now = now or datetime.now()
    d = parse_stored_due(task.get("due", "")) if task.get("due") else None

    if time_scope == "any":
        return True
    if time_scope == "today":
        if not d:
            return False
        return d.date() == now.date() or d < now
    if time_scope == "week":
        return bool(d and d <= (now + timedelta(days=7)))
    if time_scope == "month":
        return bool(d and d <= (now + timedelta(days=30)))
    if time_scope == "custom":
        if custom_date is None:
            return False
        return bool(d and d.date() <= custom_date)
    return True


def passes_filter(
    task: dict,
    settings: dict,
    category_scope: str,
    time_scope: str,
    custom_date: Optional[date] = None,
    now: Optional[datetime] = None,
) -> bool:
    return (
        passes_category_filter(task, category_scope)
        and priority_visible(task, settings)
        and passes_time_filter(task, category_scope, time_scope, custom_date, now)
    )


def search_match(task: dict, query: str) -> bool:
    if not query:
        return True
    q = query.lower()
    return (q in task.get("title", "").lower()) or (q in task.get("notes", "").lower())


def sort_key_for(task: dict, col: str):
    if col == "id":
        return task["id"]
    if col == "due":
        return parse_stored_due(task.get("due", "")) if task.get("due") else datetime.max
    if col == "prio":
        return PRIORITY_ORDER.get((task.get("priority", "M") or "M").upper(), 99)
    if col == "rep":
        return task.get("repeat", "")
    if col == "title":
        return task.get("title", "").lower()
    if col == "notes":
        return task.get("notes", "").lower()
    if col == "times":
        return task.get("times_completed", 0)
    return 0
