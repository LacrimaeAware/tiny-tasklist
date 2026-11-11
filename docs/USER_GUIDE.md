# User guide

Tiny Tasklist keeps one-off tasks and repeating habits in a desktop task list.
Run `python -m tasklistprogram` from the repository root. The optional
[browser prototype](#browser-prototype) is described below. The
[import format](IMPORTING.md) page has the complete due-date grammar.

## Desktop window

The top row contains Title, Due, Priority, Repeat, Notes, Add and Stats. Enter a
title and click **Add**, or press Enter in Notes. Shift+Enter in Title adds a
Medium-priority task due tomorrow. Choosing Daily priority also sets daily repeat.
Ultra priority is set by skipped-task escalation rather than the add form.

The filter row controls Category, Time, Search, minimum priority and Group view.
Search matches titles and notes. Click a table heading to sort, then click again
to reverse the order. Double-click a group header to expand or collapse it.
The bottom bar shows the number of visible rows, open tasks and completions today.
**View → Toggle Dark Mode** changes the theme and remembers the choice.

**Today** shows active tasks due today or earlier. An undated task is visible only
with Time set to **any**. The desktop's **all** category still hides completed,
deleted and suspended tasks; use their separate categories to view them.

## Editing and scheduling

Double-click a task, or right-click and choose **Edit → Manual Edit**, to change
its title, due date, priority, repeat, group or notes. Choosing **custom** repeat
asks for the number of days between occurrences. Other repeats are daily,
weekdays, weekly, bi-weekly and monthly.

Select several rows and use the right-click **Edit** submenu to set their
priority, repeat, due date or group together. **Bump** moves their due dates by
one day or one week in either direction.

**Mark Done** records a completion. A one-off task leaves the active list; a
recurring task records the date and advances to its next scheduled occurrence.
The app catches up missed recurring dates at startup and midnight. **Delete** is
reversible from the deleted category; **Hard Delete** asks for confirmation.
**Suspend** hides a task until it is unsuspended.

## Notes and journal

Right-click **Open Document** to open a task's Markdown file under
`tasklistprogram/data/task_documents/<Group>/<Title>-<id>.md`. Its top section
matches the task's Notes field. Text below the `Private notes` divider stays in
the file and is preserved when the displayed notes change. Reopening the document
through the app reads edits to the top section back into the task.

**Journal → Journal** adds a timestamped entry to today's Markdown file.
Completing a task also adds a line under **Completed Tasks**. Journals live under
`tasklistprogram/data/journals/YYYY/MM/`. **Mantras** opens or edits the separate
`mantras.md` file; Settings controls its daily startup popup.

## Reminders and settings

**File → Settings** controls reminders, their checkpoint count and minimum
priority, skipped-task escalation, and the mantra popup. Reminders appear as a
clock in the table and in **File → Reminders**, where they can be acknowledged.
They are not system notifications.

Skipped-task escalation is on by default. Two missed recurring occurrences raise
priority to High; three raise it to Ultra. Completing the task restores its
original priority. Settings can disable escalation or reset it for all tasks.

**File → Import Tasks** reads a text file; **Import (paste text)** accepts pasted
lines. Both use the [same import format](IMPORTING.md) as the browser server.

Delete soft-deletes the selected tasks; Ctrl+Enter marks them done. Enter in Notes
adds a task, and Shift+Enter in Title quick-adds it for tomorrow.

## Browser prototype

### Run the browser prototype

From the repository root run `python -m tasklistprogram.webserver` and open
`http://127.0.0.1:8000`. The server accepts connections from this computer only. A
"Connected to your local data" banner appears on the Today view. Opening
`web/index.html` directly shows a sample-data demo: changes are not saved, imports
use titles only, and due dates accept only `today`, `tomorrow`, `+Nd` and
`YYYY-MM-DD`. A server connection error is shown without switching to demo data.

### The page

- **Sidebar**: the categories Active, Overdue, Repeating, Completed, Suspended,
  Deleted and All, each with a count, then your groups. Click a group to show only
  that group; click it again to clear the focus. On narrow screens the sidebar opens
  from the menu button.
  **All** includes completed and suspended tasks; deleted tasks stay in **Deleted**.
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
system preference until you pick one. The first visit opens Active with **When**
set to **Any time**, so undated tasks are visible.

### Adding a task

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

### Completing tasks

Click the circle in front of a task. A toast offers **Undo**. A one-off task moves to
Completed. A repeating task records the completion in its history and moves to its
next occurrence after today, staying in the list as a fresh item; it never shows under
Completed.

Repeating tasks whose day has passed are rolled forward each time the page loads its
tasks (for example on refresh). With hazard escalation enabled, which is the default,
each missed occurrence raises the task's skip count: after two skips the priority
becomes High and after three Ultra, marked with a warning sign, until the task is
completed or you choose **Reset hazard escalation** in the gear menu.

### Editing, suspending, deleting

Click a task, or right-click it (or use its menu button), for **Edit**, **Mark done**,
**Suspend** and **Delete**. Suspended tasks leave the active views until unsuspended.
Delete moves a task to the Deleted view and offers Undo; from the Deleted view the
menu offers **Restore** and **Delete permanently**, which asks for confirmation and
cannot be undone.

### Importing tasks

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
and kept as `tasks_gui.json.premigration`. If it cannot be read, a valid
`tasks_gui.json.bak` is used instead. If neither can be read, startup stops with an
error; repair the JSON or restore a backup and start again.
The environment variable must be set before starting the desktop so that its
store, task documents, journals and mantras all use the same folder.
