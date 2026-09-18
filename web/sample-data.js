/* Sample data for the static demo: generic tasks, not real user data.
   Shapes mirror the desktop app's task schema. Due dates are expressed as an
   offset in days from "today" so the Today / Upcoming views always look current. */

function _due(offsetDays) {
  if (offsetDays === null || offsetDays === undefined) return "";
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const SAMPLE_TASKS = [
  // School
  { id: 1, title: "CS project — milestone 2", due: _due(1), priority: "H", repeat: "none", group: "School", notes: "Push the parser branch and open a PR", done: false, times: 0 },
  { id: 2, title: "Calculus problem set 5", due: _due(0), priority: "M", repeat: "none", group: "School", notes: "Sections 3.2–3.4", done: false, times: 0 },
  { id: 3, title: "Spanish essay draft", due: _due(3), priority: "M", repeat: "none", group: "School", notes: "300 words, past tense", done: false, times: 0 },
  { id: 4, title: "Read Chapter 7", due: _due(-1), priority: "L", repeat: "none", group: "School", notes: "", done: false, times: 0 },
  { id: 5, title: "Java homework 4", due: _due(2), priority: "H", repeat: "none", group: "School", notes: "Inheritance exercises", done: false, times: 0 },

  // Lifting
  { id: 6, title: "Upper body session", due: _due(0), priority: "D", repeat: "daily", group: "Lifting", notes: "Push/pull split", done: false, times: 41, habit: true },
  { id: 7, title: "Log today's workout", due: _due(0), priority: "L", repeat: "daily", group: "Lifting", notes: "", done: true, times: 38 },

  // Health
  { id: 8, title: "Take vitamins", due: _due(0), priority: "D", repeat: "daily", group: "Health", notes: "", done: true, times: 60 },
  { id: 9, title: "Meal prep", due: _due(1), priority: "M", repeat: "weekly", group: "Health", notes: "Cook for the week", done: false, times: 12 },
  { id: 10, title: "Drink 3L water", due: _due(0), priority: "D", repeat: "daily", group: "Health", notes: "", done: false, times: 50 },

  // Life Admin
  { id: 11, title: "Pay phone bill", due: _due(5), priority: "H", repeat: "monthly", group: "Life Admin", notes: "Autopay disabled this month", done: false, times: 4 },
  { id: 12, title: "Laundry", due: _due(-2), priority: "M", repeat: "weekly", group: "Life Admin", notes: "", done: false, times: 9 },

  // Misc / Social
  { id: 13, title: "Back up laptop", due: _due(6), priority: "X", repeat: "bi-weekly", group: "Misc", notes: "External drive", done: false, times: 3 },
  { id: 14, title: "Reply to club email", due: _due(0), priority: "L", repeat: "none", group: "Social", notes: "RSVP for Friday", done: false, times: 0 },
  { id: 15, title: "Review budget", due: _due(4), priority: "M", repeat: "bi-weekly", group: "Life Admin", notes: "", done: false, times: 6 },
];
