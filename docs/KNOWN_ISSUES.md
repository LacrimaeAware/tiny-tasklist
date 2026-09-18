# Known issues

Defects and limitations of this edition as of 2026-09-17. Fixed items move to the
[changelog](CHANGELOG.md).

- **Tasks without a due date are hidden by the default view.** The page opens on
  Active with When set to Today, and the time filter drops date-less tasks, so a task
  added without a due date seems to vanish until When is set to Any time.
- **The static demo understands few due values.** Opened as a file, the page parses
  only `today`, `tomorrow`, `+Nd` and `YYYY-MM-DD` and turns anything else into
  today; the server parses the full grammar. Demo edits are not saved.
- **`GET /api/stats` counts streaks from yesterday.** Its `top_streaks` start at
  yesterday, so a habit completed every day including today reads one day short. The
  page computes its own streak and counts today.
- **`GET /api/stats` undercounts "done today" for repeating tasks.** It looks only at
  `completed_at`, which completing a repeating task clears. The page computes its card
  from `history` instead; API consumers should do the same.
- **An unreadable legacy `tasks_gui.json` is skipped silently.** If the file cannot be
  parsed and no `tasks_gui.json.bak` exists, the first start creates an empty
  database and later starts do not retry, even after the file is repaired. Fix the
  JSON before the first start, or stop the server and delete `tasks.db` to retry.
- **No settings page.** Hazard escalation is on by default; the browser can reset it
  but not turn it off. The setting lives in the `meta` table of `tasks.db`.
- **Custom repeats cannot be chosen in the form.** The repeat dropdown offers none,
  daily, weekdays, weekly, bi-weekly and monthly; `custom:N` works through the import
  and the API and displays correctly.
- **One server per data directory.** Two servers on the same store each rewrite the
  whole store on save, and the later write wins.
- **No authentication.** The server listens on loopback only, but any program running
  on the same machine can reach the API.
