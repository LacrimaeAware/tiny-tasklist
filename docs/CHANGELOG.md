# Changelog

Changes to the desktop app, browser prototype and shared task logic, newest first.
Dates are local.

## 2026-11-10

- Added the Tkinter desktop application: window, table, dialogs, task documents,
  journals, reminders and application icons.
- `python -m tasklistprogram` opens the desktop app. The browser prototype remains
  available through `python -m tasklistprogram.webserver`.
- The desktop status bar uses the shared statistics helper, so today's recurring
  completions count even after their next occurrence has been scheduled.

## 2026-11-09

- A project page shows the browser prototype, sample-data demo, local-run instructions
  and reference docs.
  The sample demo can run over HTTP with `?demo=1`; it makes no API requests.
- The first visit shows tasks from any date, including tasks without a due date.
- All includes completed and suspended tasks, with deleted tasks kept separate.
- Narrow screens give search its own toolbar row, keeping task and settings
  controls visible. Completed tasks keep readable text contrast.
- Failed browser actions show an error. An unsuccessful save keeps the form open
  and preserves its contents; a failed server connection does not load demo data.
- Import errors identify skipped lines and leave only those lines in the form for
  correction, so retrying does not duplicate successful imports.
- Habit statistics include today's completions and streak. Completion windows cover
  the last 7 and 30 calendar days, including today, and omit deleted or suspended tasks.
- Startup stops if legacy JSON and its backup cannot be read, allowing a repaired
  file to be imported on the next start.
- Static file requests must stay within the served folder, including when a sibling
  folder has a similar name.

## 2026-09-17

- Repeating tasks are rolled forward by the server whenever the page lists them. A
  habit due three days ago used to need three completions, each adding a history
  entry, to reach tomorrow; one completion now lands on the next occurrence after
  today.
- The API refuses invalid input instead of guessing: an unparseable due or an unknown
  repeat returns 400 with the same message the import gives; malformed JSON, a
  non-object body or a bad Content-Length return 400 instead of dropping the
  connection. State-changing requests must send JSON and may not come from another
  site's page (403).
- The browser edition started the server from `python -m tasklistprogram`.
  New `--port` (0 picks a free port)
  and `--data-dir` options; a busy port or a bad value prints one line, not a
  traceback.
- The Repeating view and the "best streak" card show zero until a repeating task has
  a completion, instead of placeholder numbers.
- Static mode displays a demo banner.

## 2026-06-08

- Import in the browser (gear menu, Import tasks) with the same parser as the text
  format, backed by `POST /api/import`; a "Copy AI prompt" button with a prompt that
  produces the format.
- Storage moved to SQLite (`data/tasks.db`) with one transaction per save. An
  existing `tasks_gui.json` is migrated on first run and kept as `.premigration`; the
  previous state is kept as `.bak`; one dated JSON snapshot per day, 14 kept.

## 2026-06-07

- Group view with collapsible headers; category sidebar, When and minimum-priority
  filters and search, remembered between visits.
- Deleted view with Restore and Delete permanently; hazard escalation reset in the
  gear menu.
- Editing by clicking a row or from the context menu; an Undo toast after
  completing, suspending or deleting; Suspended view; Completed ordered by recency.
- "Done today" counts repeating tasks through their history; the heatmap ignores
  suspended tasks.
- Concurrent requests handled by one server are serialized.
- Due parsing accepts bare times, `today` and `tomorrow`, month names and more in
  every field that takes a due value; a JSON file saved with a UTF-8 byte order mark
  loads.
- App icon; light and dark themes following the system preference; responsive
  layout.

## 2026-02-22

- Bi-weekly and custom (every N days) repeats; a hazard escalation reset; filtering
  split into category and time.

## 2026-01-31 to 2026-02-01

- First versions of the shared task logic: priorities, due dates, repeats, groups
  and notes; hazard escalation for skipped habits; suspension; text import.
