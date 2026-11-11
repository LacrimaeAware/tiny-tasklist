# Tiny Tasklist

A Python/Tkinter desktop app for tasks and repeating habits. It has due dates,
priorities, groups, bulk edits and reminder checkpoints. Task notes and daily
journals are Markdown files; tasks are stored in SQLite.

[Project page](https://lacrimaeaware.github.io/tiny-tasklist/)

![Tiny Tasklist desktop app with grouped sample tasks, due dates, priorities and notes](docs/images/desktop-demo.jpg)

*Desktop app with sample tasks.*

## Tasks and habits

- Flexible dates such as `tomorrow 14:00` or `+2d`.
- Sorting, groups and bulk edits to dates, priorities and groups.
- Recurring tasks with completion history and the next occurrence scheduled on completion.
- Markdown task notes and a daily journal.

## Browser prototype

The browser prototype uses the same task store and date parser.
[Open the sample demo](https://lacrimaeaware.github.io/tiny-tasklist/demo/?demo=1).
Changes in the demo are not saved.

## Reference

- [User guide](docs/USER_GUIDE.md)
- [Import format](docs/IMPORTING.md)
- [Architecture, API and build commands](docs/ARCHITECTURE.md)
- [Behavior notes](docs/KNOWN_ISSUES.md) and [changelog](docs/CHANGELOG.md)
- [Project notes](PROVENANCE.md) · [MIT license](LICENSE)
