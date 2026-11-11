# Known issues

Limitations of the desktop app and browser prototype. Fixed items are in the
[changelog](CHANGELOG.md).

## Desktop

- **Time filters hide undated tasks.** Use Time = any to see tasks with no due
  date. Today is the default on the desktop, so an undated task can disappear
  from the current view immediately after adding it.
- **Reminder acknowledgment can take several passes.** The clock chip represents
  any elapsed unacknowledged checkpoint, while the dialog shows the latest one.
- **Some dialogs stay light in dark mode.** The main window and task rows use the
  chosen palette; classic Tk widgets in some dialogs may retain light colors.
- **No completion undo.** A repeating completion advances the due date and writes
  a journal line. The desktop has no Undo button for that action.
- **Concurrent interfaces can overwrite edits.** The desktop reloads on focus and
  before midnight catch-up, but both interfaces save the whole store. Avoid
  changing tasks simultaneously in the desktop and browser.

## Browser prototype

- **The sample demo understands few due values.** It parses
  only `today`, `tomorrow`, `+Nd` and `YYYY-MM-DD`. Imports use titles only, and
  edits are not saved. Run the server for full date parsing, import and storage.
- **No settings page.** Hazard escalation is on by default; the browser can reset it
  but not turn it off. The setting lives in the `meta` table of `tasks.db`.
- **Custom repeats cannot be chosen in the form.** The repeat dropdown offers none,
  daily, weekdays, weekly, bi-weekly and monthly; `custom:N` works through the import
  and the API and displays correctly.
- **One server per data directory.** Two servers on the same store each rewrite the
  whole store on save, and the later write wins.
- **Tabs do not refresh automatically.** Reload to see changes from another tab.
  Saving an older form can replace newer values for its fields.
- **No authentication.** The server listens on loopback only, but any program running
  on the same machine can reach the API.
