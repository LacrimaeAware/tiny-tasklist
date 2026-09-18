# Architecture

Tiny Tasklist is a Python 3.13 program that uses only the standard library. A small
HTTP server (`tasklistprogram/webserver.py`) serves the static page in `web/` and a
JSON API; both sit on the `tasklistprogram/core/` package, which owns the task data
and its rules. The same core also drives a Tkinter desktop interface that lives in the
author's working repository and is not part of this edition.

```
web/ (index.html, app.js, styles.css)  <-- HTTP -->  webserver.py (routes, request checks)
                                                           |
                                                     core/ (no UI code)
                                          model   dates   scheduler   io_import
                                                           |
                                                 data/tasks.db (SQLite)
```

## Modules

### core/

- **`model.py`**: persistence and aggregates. `load_db()` reads the whole store into
  one dict; `save_db(db)` writes it back inside a single SQLite transaction, keeps the
  previous state as `tasks_gui.json.bak`, writes one dated JSON snapshot per day under
  `backups/` (14 kept) and bumps a `rev` counter. On first run a legacy
  `tasks_gui.json` in the data folder is migrated and kept as `.premigration`.
  `set_data_dir()` moves every path (the `--data-dir` option); the
  `TINYTASKLIST_DATA_DIR` environment variable does the same at import time.
  `default_settings()` and `normalize_settings()` define the settings schema;
  `stats_summary()` backs `GET /api/stats`.
- **`dates.py`**: every date rule. `parse_due_entry()` turns typed text into a
  datetime or a date-only value; `fmt_due_for_store()` and `parse_stored_due()`
  convert to and from the stored strings `YYYY-MM-DD` and `YYYY-MM-DD HH:MM`;
  `next_due()` and `repeat_interval_days()` are the recurrence arithmetic.
- **`scheduler.py`**: `advance_repeating_tasks(db, today, hazard_enabled)` rolls each
  repeating task forward to its latest occurrence on or before today, catching up
  several missed periods at once and applying skip escalation when enabled.
- **`io_import.py`**: the pipe-delimited text format (`import_from_string`), plus the
  validators `parse_due_or_raise()` and `normalize_repeat()` that the API shares so
  both report the same messages.

### webserver.py

A `ThreadingHTTPServer` bound to `127.0.0.1`. Static files come from `web/`; the
requested path is resolved and must stay inside that folder. The API:

| Route | Effect |
|---|---|
| `GET /api/tasks` | all tasks, including deleted ones, plus settings; first rolls overdue repeating tasks forward and saves if anything moved |
| `GET /api/stats` | open count, completions today, in 7 and in 30 days, top streaks |
| `POST /api/tasks` | add a task; 201 with the stored task |
| `PATCH /api/tasks/{id}` | change any subset of fields; also used by Undo to restore a snapshot |
| `POST /api/tasks/{id}/toggle`, `POST /api/tasks/{id}/done` | complete (a repeating task lands on its next occurrence after today) or, with `toggle`, un-complete |
| `DELETE /api/tasks/{id}` | soft delete (`is_deleted`); `POST /api/tasks/{id}/harddelete` removes the row |
| `POST /api/hazard/reset` | clear skip counts and restore base priorities |
| `POST /api/import` | `{"text": "..."}` in the import format; returns added and failed counts with per-line details |

A task as sent to the page: `id, title, due, priority, repeat, group, notes, done,
completed_at, times, suspended, skip_count, is_deleted, history`.

Request checks, applied to every POST, PATCH and DELETE:

- An `Origin` or `Referer` header must name this server (`http://127.0.0.1:<port>` or
  `http://localhost:<port>`) or be absent; anything else is answered 403. Browsers add
  these headers to cross-site requests, so a page from another site cannot drive the
  server while it runs; local tools such as curl send neither.
- A request with a body must send `Content-Type: application/json` (415 otherwise);
  the body must be one JSON object of at most 1 MiB (400 or 413); an unparseable
  `due` or an unknown `repeat` is refused with 400 and the wording the import uses.
- Unexpected errors are answered with a JSON 500; the connection is never dropped.

Every request reads the store fresh, and a process-wide lock serializes the
read-modify-write of state-changing requests. Run one server per data directory.

### web/

`index.html`, `styles.css` and `app.js`, with no build step. On load `app.js` requests
`GET /api/tasks`; when that fails (the page was opened as a file) it falls back to
`sample-data.js` and shows the sample-data banner. Filtering, sorting, the stat cards
and the heatmap are computed in the page from the task list; the category rules
mirror the ones the core applies.

## Data flow

1. Page load: `GET /api/tasks`. The server loads the store, rolls overdue repeating
   tasks forward, saves if anything moved, and returns everything.
2. An action (add, edit, complete, suspend, delete, import) is one request. The
   server loads the store, validates and applies the change under the lock, saves,
   and returns the stored task; the page replaces its copy with the response.
3. Undo: the page keeps a snapshot of the task from before a completion and sends it
   back with `PATCH` (due, completed_at, times, history, suspension).

## Storage

`data/tasks.db` has two tables: `tasks(id INTEGER PRIMARY KEY, data TEXT)` with one
JSON blob per task, and `meta(key, value)` holding `version`, `next_id`, `settings`
and `rev`. `load_db()` returns:

```json
{
  "version": 1,
  "next_id": 42,
  "_rev": 17,
  "settings": {"hazard_escalation_enabled": true, "...": "see default_settings()"},
  "tasks": [
    {
      "id": 1, "title": "Example", "notes": "", "priority": "M",
      "due": "2026-06-07 14:00", "repeat": "weekly",
      "created_at": "2026-06-01T09:00:00", "completed_at": "",
      "times_completed": 3, "history": ["2026-05-24", "2026-05-31"],
      "is_deleted": false, "is_suspended": false, "skip_count": 0, "group": "Work"
    }
  ]
}
```

Optional fields appear once used: `base_priority` (the priority saved during hazard
escalation), `deleted_at`, `updated_at`. Fields the desktop interface writes
(`doc_path`, `bumped_count`, `acknowledged_checkpoints`) are preserved but unused
here.

## Behaviors worth knowing

- **Repeating tasks reset rather than archive.** Completing one records the date in
  `history`, increments `times_completed`, clears `completed_at` and moves `due` to
  the next occurrence after today. Completed repeating tasks therefore never appear
  under Completed.
- **Catch-up.** The desktop interface advances repeating tasks at launch and at
  midnight; this server does it on every task listing with the same core function,
  so a daily task due three days ago is at today, with three skips, before you see it.
- **Hazard escalation.** With `hazard_escalation_enabled` (on by default), each
  missed occurrence raises `skip_count`; two skips set the priority to High (the
  original goes to `base_priority`), three set Ultra. Completing the task or
  `POST /api/hazard/reset` restores it.

## Tests

`python -m unittest discover -s tests`. `test_dates`, `test_scheduler`,
`test_io_import` and `test_model` cover the core (the store tests use a temporary
directory); `test_webserver` covers the adapter functions; `test_webserver_http`
starts a real server on a free port with a temporary data directory and exercises
routing, the request checks, catch-up, persistence and the command line;
`test_web_assets` checks that the web files exist and, if Node is installed, that the
scripts parse.
