import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from .dates import parse_stored_due

ROOT_DIR = Path(__file__).resolve().parent.parent
# Data location can be overridden (e.g. a synced folder, or a separate DB for the
# web server) via the TINYTASKLIST_DATA_DIR environment variable.
_ENV_DATA_DIR = os.environ.get("TINYTASKLIST_DATA_DIR")
DATA_DIR = Path(_ENV_DATA_DIR) if _ENV_DATA_DIR else (ROOT_DIR / "data")
DB_FILE = DATA_DIR / "tasks.db"            # primary store (SQLite)
DATA_FILE = DATA_DIR / "tasks_gui.json"    # legacy JSON (migrated from, then kept as .premigration)
BACKUP_FILE = DATA_DIR / "tasks_gui.json.bak"
BACKUP_DIR = DATA_DIR / "backups"
DAILY_BACKUPS_KEEP = 14  # ~2 weeks of point-in-time recovery; cheap (one write/day)
LEGACY_DATA_FILE = ROOT_DIR / "tasks_gui.json"
LEGACY_BACKUP_FILE = ROOT_DIR / "tasks_gui.json.bak"

def set_data_dir(path) -> None:
    """Point the store at *path* (used by the web server's --data-dir option and by tests)."""
    global DATA_DIR, DB_FILE, DATA_FILE, BACKUP_FILE, BACKUP_DIR
    DATA_DIR = Path(path)
    DB_FILE = DATA_DIR / "tasks.db"
    DATA_FILE = DATA_DIR / "tasks_gui.json"
    BACKUP_FILE = DATA_DIR / "tasks_gui.json.bak"
    BACKUP_DIR = DATA_DIR / "backups"

def _load_json(path: Path):
    # utf-8-sig tolerates a UTF-8 BOM (e.g. if the file was saved by Notepad or
    # PowerShell) while still reading plain UTF-8 correctly.
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)

def _atomic_write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)

def default_settings():
    return {
        "reminders_enabled": False,
        "reminder_count": 4,
        "reminder_min_priority": "M",
        "hazard_escalation_enabled": True,
        "mantras_autoshow": True,
        "min_priority_visible": "L",
        "ui_category_scope": "active",
        "ui_time_scope": "today",
        "ui_time_custom_date": "",
        "ui_theme": "light",
    }

def normalize_settings(settings: dict) -> dict:
    merged = default_settings()
    incoming = dict(settings or {})

    legacy_scope = incoming.pop("ui_filter_scope", None)
    if legacy_scope:
        if legacy_scope in ("today", "week"):
            incoming.setdefault("ui_time_scope", legacy_scope)
            incoming.setdefault("ui_category_scope", "active")
        elif legacy_scope == "overdue":
            incoming.setdefault("ui_time_scope", "any")
            incoming.setdefault("ui_category_scope", "overdue")
        elif legacy_scope in ("all", "repeating"):
            incoming.setdefault("ui_time_scope", "any")
            incoming.setdefault("ui_category_scope", "active" if legacy_scope == "all" else "repeating")
        elif legacy_scope in ("done", "deleted", "suspended"):
            incoming.setdefault("ui_time_scope", "any")
            incoming.setdefault("ui_category_scope", legacy_scope)

    merged.update(incoming)
    return merged

# ===== SQLite storage =====
# Tasks are stored one per row as JSON; meta holds version / next_id / settings / rev.
# A save replaces the task and metadata rows in one SQLite transaction.

def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")     # better concurrency across processes
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()

def _read_all(conn: sqlite3.Connection) -> dict:
    tasks = [json.loads(r[0]) for r in conn.execute("SELECT data FROM tasks ORDER BY id")]
    meta = {k: json.loads(v) for k, v in conn.execute("SELECT key, value FROM meta")}
    next_id = meta.get("next_id")
    if not isinstance(next_id, int) or next_id < 1:
        next_id = (max((t.get("id", 0) for t in tasks), default=0) + 1)
    return {
        "version": meta.get("version", 1),
        "next_id": next_id,
        "settings": meta.get("settings", {}),
        "tasks": tasks,
        "_rev": meta.get("rev", 0),
    }

def _write_all(conn: sqlite3.Connection, db: dict) -> int:
    rev = 0
    row = conn.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
    if row:
        try:
            rev = int(json.loads(row[0]))
        except Exception:
            rev = 0
    new_rev = rev + 1
    with conn:  # single atomic transaction
        conn.execute("DELETE FROM tasks")
        conn.executemany(
            "INSERT INTO tasks(id, data) VALUES(?, ?)",
            [(t["id"], json.dumps(t)) for t in db.get("tasks", [])],
        )
        conn.execute("DELETE FROM meta")
        conn.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", [
            ("version", json.dumps(db.get("version", 1))),
            ("next_id", json.dumps(db.get("next_id", 1))),
            ("settings", json.dumps(db.get("settings", {}))),
            ("rev", json.dumps(new_rev)),
        ])
    return new_rev

def _migrate_from_json_if_needed(conn: sqlite3.Connection) -> None:
    """One-time import of the legacy JSON into SQLite, preserving the original file."""
    if conn.execute("SELECT 1 FROM tasks LIMIT 1").fetchone():
        return
    if conn.execute("SELECT 1 FROM meta LIMIT 1").fetchone():
        return
    if not DATA_FILE.exists():
        return  # fresh install, nothing to migrate
    try:
        data = _load_json(DATA_FILE)
    except (OSError, ValueError) as error:
        try:
            data = _load_json(BACKUP_FILE)
        except (OSError, ValueError):
            raise ValueError(
                "Could not read legacy tasks_gui.json or its backup. Repair the JSON "
                "or restore a valid tasks_gui.json.bak before restarting."
            ) from error
    _write_all(conn, data)
    # Keep the original JSON forever as a safety copy (do not delete).
    try:
        DATA_FILE.replace(DATA_FILE.parent / (DATA_FILE.name + ".premigration"))
    except OSError:
        pass

def current_rev():
    """Cheap read of the store's revision counter (for change detection). None on error."""
    try:
        conn = _connect()
        _init_schema(conn)
        row = conn.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
        conn.close()
        return int(json.loads(row[0])) if row else 0
    except Exception:
        return None

def load_db():
    # Legacy: a JSON file left at the repo root migrates into the data dir first.
    if not DB_FILE.exists() and not DATA_FILE.exists() and LEGACY_DATA_FILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LEGACY_DATA_FILE.replace(DATA_FILE)
        if LEGACY_BACKUP_FILE.exists():
            LEGACY_BACKUP_FILE.replace(BACKUP_FILE)
    conn = _connect()
    try:
        _init_schema(conn)
        _migrate_from_json_if_needed(conn)
        db = _read_all(conn)
    finally:
        conn.close()
    if "version" not in db:
        db["version"] = 1
    db["settings"] = normalize_settings(db.get("settings", {}))
    return db

def _rotate_daily_backup(payload: dict):
    """Keep one dated snapshot per day under data/backups/, pruned to the last N.

    Cheap insurance against corruption / bad edits: at most one extra write per day,
    capped at DAILY_BACKUPS_KEEP files. Never allowed to break a save.
    """
    try:
        daily = BACKUP_DIR / f"tasks_gui_{date.today().isoformat()}.json"
        if daily.exists():
            return
        _atomic_write_json(daily, payload)
        snaps = sorted(BACKUP_DIR.glob("tasks_gui_*.json"))
        for old in snaps[:-DAILY_BACKUPS_KEEP]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        pass

def save_db(db):
    conn = _connect()
    _init_schema(conn)
    # .bak = the previous stored state as readable JSON, for manual recovery.
    try:
        prev = _read_all(conn)
        if prev["tasks"] or prev["settings"]:
            _atomic_write_json(BACKUP_FILE, prev)
    except Exception:
        pass
    new_rev = _write_all(conn, db)
    conn.close()
    db["_rev"] = new_rev  # keep the caller's dict in sync so it knows its own write
    _rotate_daily_backup(db)

def get_task(db, tid: int):
    for t in db["tasks"]:
        if t["id"] == tid:
            return t
    return None

def delete_task(db, tid: int):
    db["tasks"] = [t for t in db["tasks"] if t["id"] != tid]

def stats_summary(db):
    today = date.today()
    seven = today - timedelta(days=6)
    thirty = today - timedelta(days=29)

    done_today = 0
    done_7 = 0
    done_30 = 0
    open_count = 0

    for t in db["tasks"]:
        if t.get("is_deleted") or t.get("is_suspended"):
            continue
        repeating = (t.get("repeat") or "none").lower() != "none"
        if not t.get("completed_at"):
            open_count += 1
        completed_days = set()
        values = t.get("history", []) if repeating else [t.get("completed_at", "")]
        for value in values:
            try:
                completed_days.add(date.fromisoformat(str(value)[:10]))
            except ValueError:
                continue
        for completed in completed_days:
            if completed == today:
                done_today += 1
            if seven <= completed <= today:
                done_7 += 1
            if thirty <= completed <= today:
                done_30 += 1

    def streak_for(t):
        hist = set(t.get("history", []))
        if not hist:
            return 0
        streak = 0
        d = today if today.isoformat() in hist else today - timedelta(days=1)
        while d.isoformat() in hist:
            streak += 1
            d -= timedelta(days=1)
        return streak

    streaks = []
    for t in db["tasks"]:
        if not t.get("is_deleted") and not t.get("is_suspended") and (t.get("repeat") or "").lower() not in ("", "none"):
            streaks.append((t["title"], streak_for(t)))

    streaks.sort(key=lambda x: x[1], reverse=True)
    top5 = streaks[:5]

    return {
        "open": open_count,
        "done_today": done_today,
        "done_7": done_7,
        "done_30": done_30,
        "top_streaks": top5
    }
