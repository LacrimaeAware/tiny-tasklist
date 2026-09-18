# Provenance

This repository is the browser edition of Tiny Tasklist. It was exported on
2026-09-17 from the author's private working repository into a new repository with
a fresh history; the commits here do not reproduce the working history.

## What is included

- `tasklistprogram/core/`: the shared task logic (SQLite store, date parsing,
  recurrence, text import).
- `tasklistprogram/webserver.py` and `web/`: the local HTTP server with its JSON API
  and the page it serves; `python -m tasklistprogram` starts it.
- `tests/`: the tests that run without a desktop toolkit (127 at export time).
- `docs/`: user guide, import format, architecture, changelog and known issues,
  written for this edition, plus the screenshot.
- `LICENSE` (MIT), unchanged.

## What stays in the working repository

- The Tkinter desktop interface (`app.py`, `ui/`, `core/actions.py`,
  `core/documents.py`, `core/reminders.py`, `core/filters.py`, `core/constants.py`)
  with its launchers, tests and user guide. It shares this core and this store.
  Reminders, per-task notes files, a daily journal, mantras, bulk edits, custom date
  filters and a settings dialog exist only there.
- Planning notes, design discussions and idea lists; editor configuration; the icon
  generator (`tools/make_icon.py`, which needs Pillow); the Poetry lock file.

## Authorship

Developed with AI assistance; design decisions, reviews and the claims in these
documents are the author's.
