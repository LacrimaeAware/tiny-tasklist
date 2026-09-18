# User guide

Tiny Tasklist keeps one-off tasks and repeating habits in one list. This guide covers
the browser interface; the [README](../README.md) explains how to start it and the
[import format](IMPORTING.md) page has the complete due-date grammar.

## Starting

From the repository root run `python -m tasklistprogram` and open
`http://127.0.0.1:8000`. The server accepts connections from this computer only. A
green banner on the Today view confirms the page is connected to the server. A
"sample data" banner means you opened `web/index.html` directly and are looking at
the built-in demo: edits stay in memory, and only `today`, `tomorrow`, `+Nd` and
`YYYY-MM-DD` are understood as due values.

## The page

- **Sidebar**: the categories Active, Overdue, Repeating, Completed, Suspended,
  Deleted and All, each with a count, then your groups. Click a group to show only
  that group; click it again to clear the focus. On narrow screens the sidebar opens
  from the menu button.
- **Top bar**: search (matches titles and notes as you type), **+ Add task**, the
  theme toggle and the gear menu.
- **Filter bar**: **When** (Any time, Today, This week, This month), a minimum
  priority, and **Group**, which turns on collapsible group headers and a
  **Collapse all** button.
- **Today view** (Active with When set to Today): cards for open tasks, tasks done
  today, tasks due this week and the best current streak.
- **Repeating view**: a 13-week heatmap of the habit with the most completions and
  its current streak.

Filter, group and theme choices are remembered by the browser. The theme follows the
system preference until you pick one.

## Adding a task

**+ Add task** opens a form with title (required), due, priority, repeat, group and
notes. Due accepts dates (`2026-10-05`, `10/05`), times (`14:00`, `1400`, or a date
followed by a time), `today`, `tomorrow`, weekday names, month names (`Sept 29`),
dayparts (`morning`, `noon`, `afternoon`, `evening`), `midnight` and relative tokens
such as `+2d +3h` (`d` days, `h` hours, `m` minutes, `w` weeks); the full list is in
[IMPORTING.md](IMPORTING.md#field-values). A value the server cannot parse is refused
with a message and nothing is saved.

Priorities: Ultra, High, Medium (the default), Low, Daily and Misc. Choosing
**Daily** sets the repeat to daily. Repeats: none, daily, weekdays, weekly, bi-weekly
(every 14 days) and monthly (same day next month, clamped to the month's length). The
import also accepts `custom:N` for every N days.

Tasks without a due date show only when **When** is **Any time**.

## Completing tasks

Click the circle in front of a task. A toast offers **Undo**. A one-off task moves to
Completed. A repeating task records the completion in its history and moves to its
next occurrence after today, staying in the list as a fresh item; it never shows under
Completed.

Repeating tasks whose day has passed are rolled forward each time the page loads its
tasks (for example on refresh). With hazard escalation enabled, which is the default,
each missed occurrence raises the task's skip count: after two skips the priority
becomes High and after three Ultra, marked with a warning sign, until the task is
completed or you choose **Reset hazard escalation** in the gear menu.

## Editing, suspending, deleting

Click a task, or right-click it (or use its menu button), for **Edit**, **Mark done**,
**Suspend** and **Delete**. Suspended tasks leave the active views until unsuspended.
Delete moves a task to the Deleted view and offers Undo; from the Deleted view the
menu offers **Restore** and **Delete permanently**, which asks for confirmation and
cannot be undone.

## Importing tasks

Gear menu, **Import tasks**: paste one task per line in the
[import format](IMPORTING.md), for example:

```
Buy groceries
Midterm exam | due: 10/13 14:00 | prio: H | group: School | notes: bring calculator
Daily standup | repeat: daily | prio: D | group: Work
```

The result reports how many lines were added and which were skipped, with the
reason. **Copy AI prompt** copies a ready-made prompt for turning a messy list into
this format.

## Where your data is

Tasks live in `tasklistprogram/data/tasks.db`. Each save also writes the previous
state to `tasks_gui.json.bak` and one dated snapshot per day under `backups/` (the
last 14 are kept). Set the `TINYTASKLIST_DATA_DIR` environment variable or start the
server with `--data-dir DIR` to use another folder. A `tasks_gui.json` file from an
older version found in the data folder is imported into the database on first start
and kept as `tasks_gui.json.premigration`.
