# Changelog

User-facing changes to the browser interface and the shared core, newest first.
Dates are local.

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
- `python -m tasklistprogram` starts the server. New `--port` (0 picks a free port)
  and `--data-dir` options; a busy port or a bad value prints one line, not a
  traceback.
- The Repeating view and the "best streak" card show zero until a repeating task has
  a completion, instead of placeholder numbers.
- The static mode is called a demo in the banner and in comments.

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
- Concurrent requests to the server are serialized so two saves cannot lose data.
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
