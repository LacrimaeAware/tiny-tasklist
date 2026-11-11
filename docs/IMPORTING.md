# Importing tasks

On the desktop, choose **File → Import Tasks…** to open a text file or
**File → Import (paste text)…** to paste lines. In the browser, use the gear menu's
**Import tasks** dialog.

The desktop and browser server use the format below. The static demo imports
titles only.

## The format (one task per line)

```
Title | due: <value> | prio: <H|M|L|D|Misc> | repeat: <value> | group: <name> | notes: <free text>
```

- **Only the title is required.** Add other fields only when you know them; omit the rest.
- Fields are separated by `|`. **Never use `|` inside a field** (it is the delimiter).
- The first part with no `key:` is the title. If a **title contains a colon**, write it
  as `title: Meeting: standup` so it is not mistaken for a field.
- Lines starting with `#` are ignored (comments); blank lines are skipped; a leading
  `- ` bullet is stripped.
- Field keys accept short aliases: `due|d`, `prio|priority|p`, `repeat|r`, `group|g`,
  `notes|n`, `title|t`.

## Field values

| Field | Accepted values |
|---|---|
| **prio** | `H` (high), `M` (medium), `L` (low), `D` (daily habit; sets a daily repeat), `Misc`. Do not use `U`/Ultra; that priority is set by hazard escalation. Unknown values become `M`. |
| **repeat** | `none`, `daily`, `weekdays`, `weekly`, `bi-weekly`, `monthly`, or `custom:N` (every N days; N a positive integer). |
| **group** | a short Title-Case category, e.g. `Health`, `School`, `Life Admin`. |
| **due** | see below |

**Due accepts:** `YYYY-MM-DD`, `YYYY-MM-DD HH:MM`, `MM/DD`, `MM/DD HH:MM`,
`HH:MM` or `HHMM` (today at that time), `today` / `tomorrow` / `yesterday` (optionally
followed by a time), a weekday (`mon` to `sun`), a month name and day (`Sept 29`,
optionally with a year and/or time), `morning`/`noon`/`afternoon`/`evening`,
`midnight`, or **relative tokens** like `+2d +3h` (units: `d` days, `h` hours,
`m` minutes, `w` weeks). **Do not mix** natural words with relative tokens
(`+1w friday` is invalid; pick one).

A line with an unparseable `due` or `repeat` is **skipped** and reported, so the rest
still import. The same rules and messages apply to the add and edit forms, which
refuse an invalid value instead of skipping it.

## Examples

```
Buy groceries
Calculus problem set 5 | due: 10/13 14:00 | prio: H | group: School | notes: sections 3.2-3.4
Take vitamins | repeat: daily | prio: D | group: Health
Water plants | repeat: custom:6 | prio: L | group: Home
Budget review | repeat: bi-weekly | prio: M | group: Life Admin
Pay rent | due: +5d | prio: H | group: Life Admin
Dentist | due: Sept 29 | prio: M | notes: morning slot
```

## Copy-paste prompt

The import dialog's **Copy AI prompt** button copies the text below to your
clipboard. Paste it into an AI assistant, add your raw tasks where indicated, then
paste the assistant's output into the import box.

```text
You convert a list of tasks into the import format for the "Tiny Tasklist" app.
Output ONLY the formatted lines — one task per line, no preamble, no bullets, no code fences.

Format per line:
Title | due: <value> | prio: <H|M|L|D|Misc> | repeat: <value> | group: <name> | notes: <text>

Rules:
- Only Title is required. Include a field only if it's known; omit empty fields.
- Separate fields with " | ". Never put the "|" character inside a field.
- If a title contains a colon, prefix it: "title: Meeting: standup".
- prio is one of H (high), M (medium), L (low), D (daily habit -> auto daily repeat), Misc. Never use U/Ultra.
- repeat is one of none, daily, weekdays, weekly, bi-weekly, monthly, or custom:N (every N days, N a positive integer).
- due accepts: YYYY-MM-DD, "YYYY-MM-DD HH:MM", MM/DD, "MM/DD HH:MM", HH:MM or HHMM (today),
  today/tomorrow/yesterday (optionally + a time), a weekday (mon..sun), a month name + day
  ("Sept 29", optionally + year/time), morning/noon/afternoon/evening, midnight,
  or relative tokens like "+2d +3h" (d=days, h=hours, m=minutes, w=weeks).
  Do NOT mix natural words with relative tokens (e.g. "+1w friday" is invalid).
- group is a short Title-Case category (e.g. Health, School, Life Admin).
- If you're unsure of a field, leave it out rather than guessing.

Example output:
Buy groceries
Take vitamins | repeat: daily | prio: D | group: Health
Pay rent | due: +5d | prio: H | group: Life Admin

Now convert the following into this format:
<PASTE YOUR TASKS HERE>
```
