# io_import.py
from datetime import datetime
from .dates import parse_due_entry, fmt_due_for_store

VALID_REPEATS = {"none", "daily", "weekdays", "weekly", "bi-weekly", "monthly"}
VALID_PRIOS = {"H", "M", "L", "D", "X", "MISC", "Misc", "misc"}
DUE_HELP = "Use YYYY-MM-DD, MM/DD, HH:MM, HHMM, weekday words, or relative tokens like +2d +3h."
REPEAT_HELP = "Use none/daily/weekdays/weekly/bi-weekly/monthly/custom:<days>."


def parse_due_or_raise(due_s: str):
    """Parse a user-typed due value; raise ValueError with a user-facing message otherwise.

    Shared by the import parser and the web API so both report the same wording.
    """
    parsed = parse_due_entry(due_s)
    if parsed is None:
        raise ValueError(f"invalid due '{due_s}'. {DUE_HELP}")
    return parsed


def normalize_repeat(rep) -> str:
    """Return the canonical repeat value ('none', 'daily', ..., 'custom:N') or raise ValueError."""
    rep = (rep or "none").strip().lower()
    if rep.startswith("custom:"):
        raw = rep.split(":", 1)[1].strip()
        if raw.isdigit() and int(raw) > 0:
            return f"custom:{int(raw)}"
        raise ValueError("custom repeat must be a positive day count, e.g. custom:6.")
    if rep not in VALID_REPEATS:
        raise ValueError(f"invalid repeat '{rep}'. {REPEAT_HELP}")
    return rep


def _parse_lines(lines, db, return_details: bool = False):
    """
    Parse iterable of lines and mutate db in-place.
    Returns:
      - (added_count, failed_count)
      - OR (added_count, failed_count, error_details) when return_details=True
    """
    added = 0
    failed = 0
    error_details = []

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()

        parts = [p.strip() for p in line.split("|")]

        title = ""
        due_s = ""
        prio = "M"
        rep = "none"
        notes = ""
        group = ""

        for p in parts:
            if ":" in p:
                k, v = p.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if k in ("due", "d"):
                    due_s = v
                elif k in ("prio", "priority", "p"):
                    prio = v.upper()
                elif k in ("repeat", "r"):
                    rep = v.lower()
                elif k in ("notes", "n"):
                    notes = v
                elif k in ("group", "g"):
                    group = v
                elif k in ("title", "t"):
                    title = v
            else:
                if not title and p:
                    title = p

        if not title:
            failed += 1
            error_details.append(f"Line {idx}: missing title.")
            continue

        # parse due (supports HH:MM / HHMM shortcuts via the shared entry parser)
        try:
            parsed = parse_due_or_raise(due_s) if due_s else None
        except ValueError as e:
            failed += 1
            error_details.append(f"Line {idx}: {e}")
            continue

        # normalize priority & repeat
        if prio == "D":
            rep = "daily"
        if prio not in VALID_PRIOS:
            prio = "X" if prio.upper() == "MISC" else "M"
        prio = ("X" if prio.upper() == "MISC" else prio.upper())

        try:
            rep = normalize_repeat(rep)
        except ValueError as e:
            failed += 1
            error_details.append(f"Line {idx}: {e}")
            continue

        t = {
            "id": db["next_id"],
            "title": title,
            "notes": notes,
            "priority": prio,
            "due": fmt_due_for_store(parsed) if due_s else "",
            "repeat": rep,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "completed_at": "",
            "times_completed": 0,
            "history": [],
            "is_deleted": False,
            "is_suspended": False,
            "skip_count": 0,
            "group": group.strip(),
        }
        db["tasks"].append(t)
        db["next_id"] += 1
        added += 1

    if return_details:
        return added, failed, error_details
    return added, failed


def import_from_txt(path: str, db: dict, return_details: bool = False):
    """
    Returns (added_count, failed_count) or (added_count, failed_count, error_details).
    Side effect: appends to db["tasks"] and increments db["next_id"].
    """
    with open(path, "r", encoding="utf-8") as f:
        return _parse_lines(f, db, return_details=return_details)


def import_from_string(text: str, db: dict, return_details: bool = False):
    """
    Same as file import, but takes raw text (multi-line).
    """
    return _parse_lines(text.splitlines(), db, return_details=return_details)
