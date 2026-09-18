"""Local web server for the browser interface: serves `web/` and a small JSON API
over the same `core/` logic and SQLite store as the desktop app. Standard library only.

Run from the repository root:
    python -m tasklistprogram.webserver                      # http://127.0.0.1:8000
    python -m tasklistprogram.webserver --port 8765
    python -m tasklistprogram.webserver --data-dir /tmp/demo # separate store

The server listens on 127.0.0.1 only and has no authentication: it is meant for the
person sitting at this machine. State-changing requests must carry a JSON body and
come from the page it serves (or from a local tool that sends no Origin header).
"""
import argparse
import json
import sys
import threading
import mimetypes
import traceback
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import model, scheduler
from .core.dates import fmt_due_for_store, parse_stored_due, next_due
from .core.io_import import import_from_string, normalize_repeat, parse_due_or_raise

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
HOST = "127.0.0.1"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
PRIORITIES = ("U", "H", "M", "L", "D", "X")
MAX_BODY_BYTES = 1 << 20  # task payloads and pasted imports are far smaller than 1 MiB

# Serializes the read-modify-write cycle so concurrent requests (the server is
# threaded) can't clobber each other's changes.
_DB_LOCK = threading.Lock()


class RequestError(Exception):
    """A client error answered with a JSON body and *status* instead of a traceback."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _text(value) -> str:
    """Coerce a JSON value to a stripped string ('' for null)."""
    return "" if value is None else str(value).strip()


# ---------- task <-> client adapters ----------
def to_client(t: dict) -> dict:
    return {
        "id": t["id"],
        "title": t.get("title", ""),
        "due": t.get("due", ""),
        "priority": t.get("priority", "M"),
        "repeat": t.get("repeat", "none"),
        "group": t.get("group", ""),
        "notes": t.get("notes", ""),
        "done": bool(t.get("completed_at")),
        "completed_at": t.get("completed_at", ""),
        "times": t.get("times_completed", 0),
        "suspended": bool(t.get("is_suspended")),
        "skip_count": int(t.get("skip_count", 0) or 0),
        "is_deleted": bool(t.get("is_deleted")),
        "history": t.get("history", []),
    }


def op_reset_hazard(db: dict) -> int:
    """Clear hazard escalation for all tasks (mirror the desktop reset). Returns count."""
    changed = 0
    for t in db.get("tasks", []):
        if int(t.get("skip_count", 0) or 0) != 0:
            t["skip_count"] = 0
            changed += 1
        if "base_priority" in t:
            t["priority"] = t.get("base_priority", t.get("priority", "M"))
            t.pop("base_priority", None)
            changed += 1
    return changed


def client_tasks(db: dict) -> list:
    # Return ALL tasks (including deleted) so the client can filter by category
    # exactly like the desktop, including a Deleted view with restore.
    return [to_client(t) for t in db["tasks"]]


def load_current_db() -> dict:
    """Load the store and roll repeating tasks forward to today.

    The desktop app does this at launch and at midnight from a Tk timer. The server
    has no timer, so it runs the same core function whenever tasks are listed and
    saves only when something moved. The caller must hold _DB_LOCK.
    """
    db = model.load_db()
    hazard = bool(db.get("settings", {}).get("hazard_escalation_enabled"))
    if scheduler.advance_repeating_tasks(db, today=date.today(), hazard_enabled=hazard):
        model.save_db(db)
    return db


# ---------- operations (mirror the desktop, minus Tk) ----------
def op_mark_done(t: dict) -> None:
    t["completed_at"] = datetime.now().isoformat(timespec="seconds")
    t["times_completed"] = t.get("times_completed", 0) + 1
    t.setdefault("history", []).append(date.today().isoformat())
    t["skip_count"] = 0
    if "base_priority" in t:
        t["priority"] = t.get("base_priority", t.get("priority", "M"))
        t.pop("base_priority", None)

    rep = (t.get("repeat") or "none").lower()
    if rep != "none":
        cur = t.get("due", "")
        due_dt = parse_stored_due(cur) or datetime.now()
        had_time = isinstance(cur, str) and len(cur) > 10
        # Land on the first occurrence after today. A task completed late (due several
        # periods ago) would otherwise come back still overdue and need one completion
        # per missed period, each adding a history entry.
        today = date.today()
        nd = due_dt.date()
        while True:
            step = next_due(nd, rep)
            if step is None or step <= nd:
                break  # no forward progress (unknown repeat value): keep the current due
            nd = step
            if nd > today:
                break
        t["due"] = datetime.combine(nd, due_dt.time()).strftime("%Y-%m-%d %H:%M") if had_time else nd.strftime("%Y-%m-%d")
        t["completed_at"] = ""  # recurring tasks reset for the next cycle


def op_toggle(t: dict) -> None:
    if t.get("completed_at"):
        t["completed_at"] = ""  # undo a one-off completion
    else:
        op_mark_done(t)


def op_update(t: dict, payload: dict) -> None:
    """Apply an edit to a task (used by PATCH). Only updates provided fields.

    Raises ValueError for an unparseable due or an unknown repeat, with the same
    wording the import uses; nothing is changed in that case because validation
    happens before the first assignment.

    Also accepts completed_at / times / history so the client can implement a
    clean Undo by restoring a pre-toggle snapshot.
    """
    new_repeat = normalize_repeat(_text(payload.get("repeat"))) if "repeat" in payload else None
    new_due = None
    if "due" in payload:
        due_s = _text(payload.get("due"))
        new_due = fmt_due_for_store(parse_due_or_raise(due_s)) if due_s else ""

    if "title" in payload:
        title = _text(payload.get("title"))
        if title:
            t["title"] = title
    if "notes" in payload:
        t["notes"] = "" if payload.get("notes") is None else str(payload.get("notes"))
    if "group" in payload:
        t["group"] = _text(payload.get("group"))
    if new_repeat is not None:
        t["repeat"] = new_repeat
    if "priority" in payload:
        p = _text(payload.get("priority")) or "M"
        p = "X" if p.lower() == "misc" else p.upper()
        if p in PRIORITIES:
            t["priority"] = p
            if p == "D":
                t["repeat"] = "daily"  # mirror the desktop Edit dialog
    if new_due is not None:
        t["due"] = new_due
    if "is_suspended" in payload:
        t["is_suspended"] = bool(payload["is_suspended"])
    if "is_deleted" in payload:
        t["is_deleted"] = bool(payload["is_deleted"])  # lets the client undo a delete
    # Fields below let the client restore a snapshot for Undo.
    if "completed_at" in payload:
        t["completed_at"] = payload.get("completed_at") or ""
    if "times" in payload:
        try:
            t["times_completed"] = int(payload["times"])
        except (TypeError, ValueError):
            pass
    if "history" in payload and isinstance(payload["history"], list):
        t["history"] = payload["history"]
    t["updated_at"] = datetime.now().isoformat(timespec="seconds")


def op_add(db: dict, payload: dict) -> dict:
    """Append a new task built from *payload*. Raises ValueError on a missing title,
    an unparseable due or an unknown repeat (import wording)."""
    title = _text(payload.get("title"))
    if not title:
        raise ValueError("title required")
    due_s = _text(payload.get("due"))
    parsed = parse_due_or_raise(due_s) if due_s else None
    prio = _text(payload.get("priority")) or "M"
    prio = "X" if prio.lower() == "misc" else prio.upper()
    if prio not in PRIORITIES:
        prio = "M"
    # Daily priority forces a daily repeat (as the import and the desktop dialog do).
    rep = "daily" if prio == "D" else normalize_repeat(_text(payload.get("repeat")))
    t = {
        "id": db["next_id"],
        "title": title,
        "notes": _text(payload.get("notes")),
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
        "group": _text(payload.get("group")),
    }
    db["tasks"].append(t)
    db["next_id"] += 1
    return t


# ---------- HTTP handler ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    # -- helpers --
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        """Parse the request body as one JSON object; RequestError (400) for anything else."""
        raw_length = (self.headers.get("Content-Length") or "0").strip()
        try:
            length = int(raw_length)
        except ValueError:
            raise RequestError("invalid Content-Length")
        if length < 0:
            raise RequestError("invalid Content-Length")
        if length > MAX_BODY_BYTES:
            raise RequestError("request body too large", 413)
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise RequestError("invalid JSON body")
        if not isinstance(payload, dict):
            raise RequestError("JSON body must be an object")
        return payload

    def _find(self, db, tid):
        return next((t for t in db["tasks"] if t["id"] == tid), None)

    def _parse_id(self, raw_id) -> int:
        try:
            return int(raw_id)
        except ValueError:
            raise RequestError("bad id")

    # -- request guards --
    def _dispatch(self, route):
        """Run route(path); answer RequestError with its status and anything else with 500."""
        try:
            route(urlparse(self.path).path)
        except RequestError as e:
            self._send_json({"error": str(e)}, e.status)
        except Exception:
            traceback.print_exc()
            self._send_json({"error": "internal server error"}, 500)

    def _is_own_origin(self, url: str) -> bool:
        parts = urlparse(url)
        if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
            return False
        try:
            port = parts.port
        except ValueError:
            return False
        return (port or 80) == self.server.server_address[1]

    def _check_mutation_allowed(self):
        """Reject requests that a page from another site could send while the server runs.

        Browsers attach Origin (and usually Referer) to cross-site POST, PATCH and
        DELETE requests; our own page carries this server's origin, and tools such as
        curl send neither. A body must also be JSON: an HTML form cannot produce that
        content type without a CORS preflight, which this server does not answer.
        """
        for header in ("Origin", "Referer"):
            value = self.headers.get(header)
            if value and not self._is_own_origin(value):
                raise RequestError(f"{header.lower()} not allowed", 403)
        length = (self.headers.get("Content-Length") or "").strip()
        if length and length != "0":
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                raise RequestError("Content-Type must be application/json", 415)

    # -- routing --
    def do_GET(self):
        self._dispatch(self._route_get)

    def do_POST(self):
        self._dispatch(self._route_post)

    def do_PATCH(self):
        self._dispatch(self._route_patch)

    def do_DELETE(self):
        self._dispatch(self._route_delete)

    def _route_get(self, path):
        if path == "/api/tasks":
            with _DB_LOCK:
                db = load_current_db()
                payload = {"tasks": client_tasks(db), "settings": db.get("settings", {})}
            return self._send_json(payload)
        if path == "/api/stats":
            with _DB_LOCK:
                stats = model.stats_summary(load_current_db())
            return self._send_json(stats)
        return self._serve_static(path)

    def _route_post(self, path):
        self._check_mutation_allowed()
        if path == "/api/tasks":
            payload = self._read_json()
            with _DB_LOCK:
                db = model.load_db()
                try:
                    t = op_add(db, payload)
                except ValueError as e:
                    raise RequestError(str(e))
                model.save_db(db)
                client = to_client(t)
            return self._send_json(client, 201)
        if path == "/api/hazard/reset":
            with _DB_LOCK:
                db = model.load_db()
                count = op_reset_hazard(db)
                model.save_db(db)
            return self._send_json({"ok": True, "reset": count})
        if path == "/api/import":
            text = self._read_json().get("text", "")
            if not isinstance(text, str):
                raise RequestError("text must be a string")
            with _DB_LOCK:
                db = model.load_db()
                added, failed, details = import_from_string(text, db, return_details=True)
                if added:
                    model.save_db(db)
            return self._send_json({"added": added, "failed": failed, "details": details})
        if path.startswith("/api/tasks/") and path.endswith("/toggle"):
            return self._mutate_one(path.split("/")[3], op_toggle)
        if path.startswith("/api/tasks/") and path.endswith("/done"):
            return self._mutate_one(path.split("/")[3], op_mark_done)
        if path.startswith("/api/tasks/") and path.endswith("/harddelete"):
            return self._hard_delete(path.split("/")[3])
        raise RequestError("not found", 404)

    def _route_patch(self, path):
        self._check_mutation_allowed()
        if path.startswith("/api/tasks/") and path.count("/") == 3:
            payload = self._read_json()
            return self._mutate_one(path.split("/")[3], lambda t: op_update(t, payload))
        raise RequestError("not found", 404)

    def _route_delete(self, path):
        self._check_mutation_allowed()
        if path.startswith("/api/tasks/"):
            def _del(t):
                t["is_deleted"] = True
                t["deleted_at"] = datetime.now().isoformat(timespec="seconds")
            return self._mutate_one(path.split("/")[3], _del)
        raise RequestError("not found", 404)

    def _mutate_one(self, raw_id, fn):
        tid = self._parse_id(raw_id)
        with _DB_LOCK:
            db = model.load_db()
            t = self._find(db, tid)
            if not t:
                raise RequestError("not found", 404)
            try:
                fn(t)
            except ValueError as e:
                raise RequestError(str(e))
            model.save_db(db)
            client = to_client(t)
        return self._send_json(client)

    def _hard_delete(self, raw_id):
        tid = self._parse_id(raw_id)
        with _DB_LOCK:
            db = model.load_db()
            before = len(db["tasks"])
            db["tasks"] = [t for t in db["tasks"] if t["id"] != tid]
            if len(db["tasks"]) == before:
                raise RequestError("not found", 404)
            model.save_db(db)
        return self._send_json({"ok": True})

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        target = (WEB_DIR / path.lstrip("/")).resolve()
        # prevent path traversal outside web/
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")  # always serve fresh during dev
        self.end_headers()
        self.wfile.write(data)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tasklistprogram.webserver",
        description="Serve the Tiny Tasklist browser interface to this machine only (127.0.0.1).",
    )
    parser.add_argument("--port", type=int, default=8000,
                        help="port on 127.0.0.1 (default 8000; 0 picks a free port)")
    parser.add_argument("--data-dir", metavar="DIR",
                        help="directory for tasks.db and its backups (default: tasklistprogram/data, "
                             "or the TINYTASKLIST_DATA_DIR environment variable)")
    args = parser.parse_args(argv)
    if args.data_dir:
        model.set_data_dir(args.data_dir)
    try:
        server = ThreadingHTTPServer((HOST, args.port), Handler)
    except OSError as e:
        print(f"Could not listen on {HOST}:{args.port}: {e.strerror or e}", file=sys.stderr)
        return 1
    port = server.server_address[1]
    print(f"Tiny Tasklist at http://{HOST}:{port}  (data: {model.DATA_DIR})", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
