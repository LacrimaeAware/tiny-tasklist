# Project notes

Tiny Tasklist's Python/Tkinter desktop application and optional browser prototype
share a SQLite store and task rules.

## What is included

- `tasklistprogram/app.py` and `ui/`: the desktop window, task list, dialogs,
  autocomplete, themes and application icons.
- `tasklistprogram/core/`: SQLite storage, date parsing, recurrence, filters,
  imports, desktop actions, Markdown notes, journals and reminder checkpoints.
- `tasklistprogram/webserver.py` and `web/`: the local HTTP server with its JSON API
  and the optional browser prototype.
- `tests/`: core, desktop-logic, HTTP and browser-script checks using temporary stores.
- `docs/`: user guide, import format, architecture, changelog, known issues and
  screenshots of the desktop app and browser prototype with invented tasks.
- `LICENSE`: MIT.

## Scope

The application runs from a source checkout with Python's standard library and
Tkinter. `python -m tasklistprogram` opens the desktop;
`python -m tasklistprogram.webserver` starts the browser prototype. A new data
folder starts with an empty store. The browser's sample-data demo does not save
changes.

Generated with AI.
