# Architecture

Tiny Tasklist uses Python 3.13 and its standard library, including Tkinter for the
desktop window. The desktop and optional browser prototype share SQLite storage,
date parsing, recurrence and import rules. The desktop also maintains task notes
and journals as Markdown files.

```
__main__.py -> app.py + ui/         web/ <-- HTTP --> webserver.py
                     |                                  |
              core/actions                  model / dates / scheduler / io_import
                     |                                  |
              core/documents                     data/tasks.db (SQLite)
                     |
         task_documents/ + journals/ + mantras.md
```

## Modules

### Desktop

`python -m tasklistprogram` calls `app.main()`, which creates the Tkinter
`TaskApp`. `app.py` owns menus, input fields, filters, sorting and the midnight
timer; `core/actions.py` supplies the task and bulk-edit callbacks.

`ui/listview.py` renders the task table and collapsible group headers.
`ui/dialogs.py` contains editing, settings, statistics, import, journal, mantra and
reminder dialogs. `ui/controls.py` provides autocomplete; `ui/theme.py` defines
the light and dark palettes. Application icons are under `ui/assets/`.

The desktop loads the store on startup and checks its revision when the window
regains focus. The midnight reset checks for a newer revision before advancing
recurring tasks. The application writes whole-store snapshots, so simultaneous
edits in separate interfaces can still overwrite one another.

### core/

- **`model.py`**: persistence and aggregates. `load_db()` reads the whole store into
  one dict; `save_db(db)` writes it back inside a single SQLite transaction, keeps the
  previous state as `tasks_gui.json.bak`, writes one dated JSON snapshot per day under
  `backups/` (14 kept) and bumps a `rev` counter. On first run a legacy
  `tasks_gui.json` in the data folder is migrated and kept as `.premigration`.
  `set_data_dir()` configures the store paths for the server's `--data-dir` option;
  `TINYTASKLIST_DATA_DIR` configures them at import time.
  `default_settings()` and `normalize_settings()` define the settings schema;
  `stats_summary()` backs the desktop Stats dialog and status bar, and
  `GET /api/stats`.
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
- **`filters.py`**: desktop category/time/priority predicates, title/notes search
  and table sort keys; **`constants.py`** holds priority codes, order and icons.
- **`actions.py`**: Tk callbacks for completion, deletion, suspension, bulk edits
  and date bumps. Completing a task writes its journal entry before saving.
- **`documents.py`**: task Markdown files, displayed/file-only note sections,
  group/title moves, dated journal entries and mantra files. It also reads
  `TINYTASKLIST_DATA_DIR` at import time, so set that variable before starting the
  desktop to keep all its files together.
- **`reminders.py`**: reminder checkpoints and the table's pending-reminder chip.

### webserver.py

A `ThreadingHTTPServer` bound to `127.0.0.1`. Static files come from `web/`; the
requested path is resolved and must stay inside that folder. The API:

| Route | Effect |
|---|---|
| `GET /api/tasks` | all tasks, including deleted ones, plus settings; first rolls overdue repeating tasks forward and saves if anything moved |
| `GET /api/stats` | active open count, completions today and in the last 7/30 calendar days including today, top streaks; excludes deleted and suspended tasks |
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
- Unexpected errors are answered with a JSON 500.

Every request reads the store fresh, and a process-wide lock serializes the
read-modify-write of state-changing requests. Run one server per data directory.

### web/

`index.html`, `styles.css` and `app.js`, with no build step. On load `app.js` requests
`GET /api/tasks`. A failed request displays an error. Opening the page as a file
or using `?demo=1` loads `sample-data.js`, with a banner stating that changes are not saved.
Filtering, sorting, the stat cards and the heatmap are computed in the page from
the task list.

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
escalation), `deleted_at`, `updated_at`, plus the desktop's `doc_path`,
`bumped_count` and `acknowledged_checkpoints`. The browser preserves those desktop
fields without using them.

## Behaviors worth knowing

- **Repeating tasks reset rather than archive.** Completing one records the date in
  `history`, increments `times_completed`, clears `completed_at` and moves `due` to
  the next scheduled occurrence. The completion is cleared immediately, so the
  task remains a recurring item rather than moving into the completed archive.
- **Catch-up.** The desktop advances missed dates at startup and midnight. The
  server advances repeating tasks on every task listing, so a
  daily task due three days ago is at today, with three skips, before you see it.
- **Hazard escalation.** With `hazard_escalation_enabled` (on by default), each
  missed occurrence raises `skip_count`; two skips set the priority to High (the
  original goes to `base_priority`), three set Ultra. Completing the task or
  `POST /api/hazard/reset` restores it.

## Tests

`python -m unittest discover -s tests`. `test_dates`, `test_scheduler`,
`test_io_import`, `test_filters`, `test_reminders` and `test_model` cover the core
(the store tests use a temporary directory). `test_desktop` checks recurring
completion, journal and note-file integration, and the status bar without opening
a window; `test_desktop_midnight` checks revision reload before the timer saves.
`test_webserver` covers the adapter functions; `test_webserver_http`
starts a real server on a free port with a temporary data directory and exercises
routing, the request checks, catch-up, persistence and the command line;
`test_web_assets` checks that the web files exist and, if Node is installed, that the
scripts parse and browser error handling preserves unsaved input and stored state.
