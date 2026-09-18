/* Tiny Tasklist — web app logic (vanilla JS, no dependencies).
   Mirrors the desktop's filtering model: Category × Time × Min-priority × Search,
   plus a collapsible Group view. */

const MS_DAY = 86400000;
const PRIO = {
  U: { label: "Ultra", icon: "🚨" }, H: { label: "High", icon: "🔴" },
  M: { label: "Med", icon: "🟠" }, L: { label: "Low", icon: "🟡" },
  D: { label: "Daily", icon: "🟢" }, X: { label: "Misc", icon: "🔵" },
};
const PRIO_RANK = { U: 5, H: 4, M: 3, L: 2, D: 1, X: 0 };
function rankOf(code) { return PRIO_RANK[(code === "Misc" ? "X" : (code || "M")).toUpperCase ? (code || "M").toUpperCase() : code] ?? 0; }

const CATEGORIES = [
  { id: "active", icon: "●", label: "Active" },
  { id: "overdue", icon: "⚠", label: "Overdue" },
  { id: "repeating", icon: "🔁", label: "Repeating" },
  { id: "done", icon: "✓", label: "Completed" },
  { id: "suspended", icon: "⏸", label: "Suspended" },
  { id: "deleted", icon: "🗑", label: "Deleted" },
  { id: "all", icon: "📋", label: "All" },
];

let tasks = SAMPLE_TASKS.slice();
let nextId = Math.max(...tasks.map((t) => t.id)) + 1;
let LIVE = false;
let editingId = null;
let _menu = null;
let _toastTimer = null;
let state = loadState();

function loadState() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem("tt_state") || "{}"); } catch (e) {}
  return {
    category: s.category || "active",
    time: s.time || "today",
    minPrio: s.minPrio || "all",
    grouped: !!s.grouped,
    collapsed: new Set(s.collapsed || []),
    group: null,    // sidebar group focus (transient)
    search: "",
  };
}
function saveState() {
  try {
    localStorage.setItem("tt_state", JSON.stringify({
      category: state.category, time: state.time, minPrio: state.minPrio,
      grouped: state.grouped, collapsed: [...state.collapsed],
    }));
  } catch (e) {}
}

/* ---------- API ---------- */
async function api(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error("api " + r.status);
  return r.json();
}
async function loadData() {
  try { tasks = (await api("GET", "/api/tasks")).tasks; LIVE = true; }
  catch (e) { tasks = SAMPLE_TASKS.slice(); LIVE = false; }
}

/* ---------- date helpers ---------- */
function startOfToday() { const d = new Date(); d.setHours(0, 0, 0, 0); return d; }
function isoDate(d) { const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function parseDue(s) { if (!s) return null; const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); }
function dayDiff(due) { return Math.round((due - startOfToday()) / MS_DAY); }
function dueChip(due) {
  if (!due) return null;
  const diff = dayDiff(due);
  if (diff < 0) return { text: "Overdue", overdue: true };
  if (diff === 0) return { text: "Today" };
  if (diff === 1) return { text: "Tomorrow" };
  if (diff < 7) return { text: due.toLocaleDateString(undefined, { weekday: "short" }) };
  return { text: due.toLocaleDateString(undefined, { month: "short", day: "numeric" }) };
}

/* ---------- filtering (mirrors core/filters.py) ---------- */
function categoryPass(t, cat) {
  const done = !!t.done, deleted = !!t.is_deleted, suspended = !!t.suspended;
  const repeating = t.repeat && t.repeat !== "none";
  if (cat === "deleted") return deleted;
  if (cat === "suspended") return suspended && !deleted;
  if (cat === "done") return done && !deleted && !suspended;
  if (deleted || suspended || done) return false;
  if (cat === "overdue") { const d = parseDue(t.due); return !!(d && d < new Date()); }
  if (cat === "repeating") return repeating;
  return true; // active / all
}
function timePass(t, cat, time) {
  if (cat === "deleted" || cat === "suspended" || cat === "done") return true;
  const d = parseDue(t.due), now = new Date();
  if (time === "any") return true;
  if (time === "today") return !!(d && dayDiff(d) <= 0);
  if (time === "week") return !!(d && d <= addDays(startOfToday(), 7));
  if (time === "month") return !!(d && d <= addDays(startOfToday(), 30));
  return true;
}
function minPrioPass(t) {
  if (state.minPrio === "all") return true;
  return rankOf(t.priority) >= rankOf(state.minPrio);
}
function searchPass(t) {
  if (!state.search) return true;
  const q = state.search.toLowerCase();
  return t.title.toLowerCase().includes(q) || (t.notes || "").toLowerCase().includes(q);
}
function filtered() {
  let list = tasks.filter((t) =>
    categoryPass(t, state.category) && timePass(t, state.category, state.time) && minPrioPass(t) && searchPass(t));
  if (state.group) list = list.filter((t) => (t.group || "Ungrouped") === state.group);
  return list;
}
function sortTasks(list) {
  return list.slice().sort((a, b) => {
    const da = parseDue(a.due), db = parseDue(b.due);
    const ta = da ? da.getTime() : Infinity, tb = db ? db.getTime() : Infinity;
    if (ta !== tb) return ta - tb;
    return rankOf(b.priority) - rankOf(a.priority);
  });
}

/* ---------- sidebar ---------- */
function categoryCount(id) { return tasks.filter((t) => categoryPass(t, id)).length; }

function renderSidebar() {
  const v = document.getElementById("views");
  v.innerHTML = "";
  CATEGORIES.forEach((c) => {
    const el = document.createElement("div");
    el.className = "nav-item" + (state.category === c.id && !state.group ? " active" : "");
    el.innerHTML = `<span class="ico">${c.icon}</span><span class="label">${c.label}</span><span class="count">${categoryCount(c.id)}</span>`;
    el.onclick = () => { state.category = c.id; state.group = null; saveState(); render(); closeSidebar(); };
    v.appendChild(el);
  });

  const groups = {};
  tasks.filter((t) => categoryPass(t, "active")).forEach((t) => { const g = t.group || "Ungrouped"; groups[g] = (groups[g] || 0) + 1; });
  const g = document.getElementById("groups");
  g.innerHTML = "";
  Object.keys(groups).sort().forEach((name) => {
    const el = document.createElement("div");
    el.className = "nav-item" + (state.group === name ? " active" : "");
    el.innerHTML = `<span class="ico">#</span><span class="label">${escapeHtml(name)}</span><span class="count">${groups[name]}</span>`;
    el.onclick = () => { state.group = state.group === name ? null : name; saveState(); render(); closeSidebar(); };
    g.appendChild(el);
  });
}

/* ---------- task rows ---------- */
function taskRow(t) {
  const due = parseDue(t.due);
  const chip = dueChip(due);
  const p = PRIO[t.priority] || PRIO.M;
  const warn = (t.skip_count > 0) ? "⚠ " : "";
  const el = document.createElement("div");
  el.className = "task" + (t.done ? " done" : "") + (t.suspended ? " suspended" : "");
  el.style.setProperty("--bar", `var(--p-${t.priority})`);

  const meta = [];
  if (t.group) meta.push(`<span class="chip group">${escapeHtml(t.group)}</span>`);
  if (chip) meta.push(`<span class="chip due${chip.overdue ? " overdue" : ""}">${chip.overdue ? "⚠ " : ""}${chip.text}</span>`);
  if (t.repeat && t.repeat !== "none") meta.push(`<span class="chip repeat">🔁 ${escapeHtml(t.repeat)}</span>`);
  if (t.times) meta.push(`<span class="chip">✓ ${t.times}×</span>`);

  el.innerHTML = `
    <div class="check" title="Toggle done">${t.done ? "✓" : ""}</div>
    <div class="body">
      <div class="title">${warn}${escapeHtml(t.title)}</div>
      ${t.notes ? `<div class="notes">${escapeHtml(t.notes)}</div>` : ""}
      <div class="meta">${meta.join("")}</div>
    </div>
    <button class="row-menu" title="Actions">⋯</button>
    <span class="prio-tag" style="background: var(--p-${t.priority})">${p.icon} ${p.label}</span>
  `;
  el.querySelector(".check").onclick = (e) => { e.stopPropagation(); toggleDone(t); };
  el.querySelector(".body").onclick = () => openModal(t);
  el.querySelector(".row-menu").onclick = (e) => { e.stopPropagation(); const r = e.target.getBoundingClientRect(); popupMenu(r.left, r.bottom + 4, rowMenuItems(t)); };
  el.oncontextmenu = (e) => { e.preventDefault(); popupMenu(e.clientX, e.clientY, rowMenuItems(t)); };
  return el;
}

function rowMenuItems(t) {
  if (t.is_deleted) {
    return [
      { label: "↩  Restore", fn: () => restoreTask(t) },
      { sep: true },
      { label: "🗑  Delete permanently", cls: "danger", fn: () => hardDelete(t) },
    ];
  }
  return [
    { label: "✎  Edit", fn: () => openModal(t) },
    { label: t.done ? "↩  Mark not done" : "✓  Mark done", fn: () => toggleDone(t) },
    { label: t.suspended ? "▶  Unsuspend" : "⏸  Suspend", fn: () => setSuspended(t, !t.suspended) },
    { sep: true },
    { label: "🗑  Delete", cls: "danger", fn: () => deleteTask(t) },
  ];
}

/* ---------- popup menu (right-click / ⋯ / gear) ---------- */
function popupMenu(x, y, items) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "context-menu";
  items.forEach((it) => {
    if (it.sep) { const s = document.createElement("div"); s.className = "sep"; m.appendChild(s); return; }
    const el = document.createElement("div");
    el.className = "item" + (it.cls ? " " + it.cls : "");
    el.textContent = it.label;
    el.onclick = () => { closeMenu(); it.fn(); };
    m.appendChild(el);
  });
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, window.innerWidth - r.width - 8) + "px";
  m.style.top = Math.min(y, window.innerHeight - r.height - 8) + "px";
  _menu = m;
}
function closeMenu() { if (_menu) { _menu.remove(); _menu = null; } }

/* ---------- mutations ---------- */
async function toggleDone(t) {
  const snap = { ...t };
  if (LIVE) { try { Object.assign(t, await api("POST", `/api/tasks/${t.id}/toggle`)); } catch (e) { t.done = !t.done; } }
  else { t.done = !t.done; }
  render();
  showToast(snap.done ? "Marked not done" : "Marked done", "Undo", () => undoToggle(snap));
}
async function undoToggle(snap) {
  if (LIVE) {
    try {
      await api("PATCH", `/api/tasks/${snap.id}`, {
        due: snap.due, completed_at: snap.completed_at || "", times: snap.times,
        history: snap.history || [], is_suspended: !!snap.suspended,
      });
      await loadData();
    } catch (e) {}
  } else { const t = tasks.find((x) => x.id === snap.id); if (t) Object.assign(t, snap); }
  render();
}
async function setSuspended(t, val) {
  if (LIVE) { try { Object.assign(t, await api("PATCH", `/api/tasks/${t.id}`, { is_suspended: val })); } catch (e) {} }
  else { t.suspended = val; }
  render();
  showToast(val ? "Suspended" : "Unsuspended", "Undo", () => setSuspended(t, !val));
}
async function deleteTask(t) {
  const snap = { ...t };
  if (LIVE) { try { await api("DELETE", `/api/tasks/${t.id}`); t.is_deleted = true; } catch (e) {} }
  else { t.is_deleted = true; }
  render();
  showToast("Deleted", "Undo", () => restoreTask(snap));
}
async function restoreTask(t) {
  if (LIVE) { try { Object.assign(t, await api("PATCH", `/api/tasks/${t.id}`, { is_deleted: false })); } catch (e) {} }
  const local = tasks.find((x) => x.id === t.id); if (local) local.is_deleted = false;
  render();
}
async function hardDelete(t) {
  if (!window.confirm(`Permanently delete "${t.title}"? This cannot be undone.`)) return;
  if (LIVE) { try { await api("POST", `/api/tasks/${t.id}/harddelete`); } catch (e) {} }
  tasks = tasks.filter((x) => x.id !== t.id);
  render();
  showToast("Permanently deleted");
}
async function resetHazard() {
  if (LIVE) { try { await api("POST", "/api/hazard/reset"); await loadData(); } catch (e) {} }
  else { tasks.forEach((t) => { t.skip_count = 0; }); }
  render();
  showToast("Hazard escalation reset");
}

/* ---------- habit heatmap ---------- */
function heatmapData(days) {
  const cells = []; let seed = 7;
  const rand = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  for (let i = days - 1; i >= 0; i--) cells.push(i < 5 ? 3 : (rand() < 0.74 ? (1 + Math.floor(rand() * 3)) : 0));
  let streak = 0; for (let i = cells.length - 1; i >= 0 && cells[i] > 0; i--) streak++;
  return { cells, streak };
}
function streakFromSet(set) {
  const today = startOfToday(); let i = set.has(isoDate(today)) ? 0 : 1, s = 0;
  for (; ; i++) { if (set.has(isoDate(addDays(today, -i)))) s++; else break; }
  return s;
}
function habitInfo() {
  const recurring = tasks.filter((t) => t.repeat && t.repeat !== "none" && !t.suspended && !t.is_deleted && Array.isArray(t.history) && t.history.length);
  if (!recurring.length) {
    // Live data with no completions yet: show an honest empty heatmap. The made-up
    // pattern is only for the static demo, whose sample tasks carry no history.
    if (LIVE) return { title: "No habit completions yet", cells: new Array(91).fill(0), streak: 0 };
    const d = heatmapData(91); return { title: "Take vitamins", cells: d.cells, streak: d.streak };
  }
  recurring.sort((a, b) => b.history.length - a.history.length);
  const t = recurring[0];
  const set = new Set(t.history.map((s) => String(s).slice(0, 10)));
  const today = startOfToday(), cells = [];
  for (let i = 90; i >= 0; i--) cells.push(set.has(isoDate(addDays(today, -i))) ? 3 : 0);
  return { title: t.title, cells, streak: streakFromSet(set) };
}
function bestStreak() {
  const wh = tasks.filter((t) => Array.isArray(t.history) && t.history.length);
  if (!wh.length) return LIVE ? 0 : heatmapData(91).streak;
  return Math.max(0, ...wh.map((t) => streakFromSet(new Set(t.history.map((x) => String(x).slice(0, 10))))));
}
function renderHeatmap(content) {
  const { title, cells, streak } = habitInfo();
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <div class="muted">Top habit · last 13 weeks</div>
    <div style="display:flex;align-items:center;gap:28px;flex-wrap:wrap;margin-top:14px">
      <div><div class="streak-big">${streak} <span>day streak</span></div></div>
      <div class="heatmap">${cells.map((l) => `<div class="cell${l ? " l" + l : ""}"></div>`).join("")}</div>
    </div>`;
  content.appendChild(card);
}

/* ---------- stats ---------- */
function isDoneToday(t) {
  const today = isoDate(startOfToday());
  if (t.completed_at) return String(t.completed_at).slice(0, 10) === today;
  if (Array.isArray(t.history) && t.history.length) return t.history.some((h) => String(h).slice(0, 10) === today);
  return !!t.done;
}
function renderStats(content) {
  const open = tasks.filter((t) => categoryPass(t, "active")).length;
  const doneToday = tasks.filter((t) => !t.is_deleted && isDoneToday(t)).length;
  const week = tasks.filter((t) => categoryPass(t, "active") && timePassRaw(t, "week")).length;
  const cards = [
    { label: "Open", value: open },
    { label: "Done today", value: doneToday },
    { label: "Due this week", value: week },
    { label: "Best streak", value: `${bestStreak()} <small>days</small>` },
  ];
  const wrap = document.createElement("div");
  wrap.className = "stats";
  wrap.innerHTML = cards.map((c) => `<div class="stat"><div class="label">${c.label}</div><div class="value">${c.value}</div></div>`).join("");
  content.appendChild(wrap);
}
function timePassRaw(t, time) { const d = parseDue(t.due); return !!(d && dayDiff(d) >= 0 && d <= addDays(startOfToday(), time === "week" ? 7 : 30)); }

/* ---------- main render ---------- */
function render() {
  renderSidebar();
  syncFilterBar();
  const catLabel = (CATEGORIES.find((c) => c.id === state.category) || {}).label || "Tasks";
  document.getElementById("viewTitle").textContent = state.group || catLabel;
  const showToday = state.category === "active" && state.time === "today" && !state.group;
  document.getElementById("viewSub").textContent = showToday ? new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) : "";

  const content = document.getElementById("content");
  content.innerHTML = "";

  if (showToday) {
    const banner = LIVE
      ? `<div class="banner">🟢 Connected to your local data.</div>`
      : `<div class="banner">✨ Static demo with sample data. Run the local server to work with your own tasks.</div>`;
    content.insertAdjacentHTML("beforeend", banner);
    renderStats(content);
  }
  if (state.category === "repeating" && !state.group) renderHeatmap(content);

  let list = filtered();
  list = (state.category === "done")
    ? list.sort((a, b) => String(b.completed_at || "").localeCompare(String(a.completed_at || "")))
    : sortTasks(list);

  if (!list.length) {
    content.insertAdjacentHTML("beforeend", `<div class="empty"><div class="big">🎉</div><div>Nothing here.</div></div>`);
    return;
  }
  if (state.grouped) renderGrouped(content, list);
  else list.forEach((t) => content.appendChild(taskRow(t)));
}

function renderGrouped(content, list) {
  const groups = {};
  list.forEach((t) => { const g = t.group || "Ungrouped"; (groups[g] = groups[g] || []).push(t); });
  const names = Object.keys(groups).sort((a, b) =>
    a === "Ungrouped" ? 1 : b === "Ungrouped" ? -1 : a.toLowerCase().localeCompare(b.toLowerCase()));
  names.forEach((name) => {
    const collapsed = state.collapsed.has(name);
    const hdr = document.createElement("div");
    hdr.className = "group-head";
    hdr.innerHTML = `<span class="caret">${collapsed ? "▶" : "▼"}</span><span class="gname">${escapeHtml(name)}</span><span class="gcount">${groups[name].length}</span>`;
    hdr.onclick = () => { if (collapsed) state.collapsed.delete(name); else state.collapsed.add(name); saveState(); render(); };
    content.appendChild(hdr);
    if (!collapsed) groups[name].forEach((t) => content.appendChild(taskRow(t)));
  });
}

/* ---------- filter bar ---------- */
function syncFilterBar() {
  document.getElementById("f_time").value = state.time;
  document.getElementById("f_minprio").value = state.minPrio;
  const gb = document.getElementById("f_group");
  gb.classList.toggle("on", state.grouped);
  document.getElementById("f_collapse").hidden = !state.grouped;
  // Time is ignored for archived categories — show a hint.
  const archived = ["done", "deleted", "suspended"].includes(state.category);
  document.getElementById("f_time").disabled = archived;
  document.getElementById("f_hint").textContent = archived ? "(time filter n/a for this view)" : "";
}

/* ---------- toast ---------- */
function showToast(msg, actionLabel, actionFn) {
  let el = document.getElementById("toast");
  if (!el) { el = document.createElement("div"); el.id = "toast"; el.className = "toast"; document.body.appendChild(el); }
  el.innerHTML = "";
  const span = document.createElement("span"); span.textContent = msg; el.appendChild(span);
  if (actionLabel && actionFn) { const b = document.createElement("button"); b.textContent = actionLabel; b.onclick = () => { hideToast(); actionFn(); }; el.appendChild(b); }
  el.classList.add("show");
  clearTimeout(_toastTimer); _toastTimer = setTimeout(hideToast, 5000);
}
function hideToast() { const el = document.getElementById("toast"); if (el) el.classList.remove("show"); }

/* ---------- modal (add + edit) ---------- */
function val(id) { return document.getElementById(id).value; }
function setVal(id, v) { document.getElementById(id).value = v; }
function openModal(task) {
  editingId = task ? task.id : null;
  document.getElementById("m_modalTitle").textContent = task ? "Edit task" : "Add a task";
  document.getElementById("m_save").textContent = task ? "Save" : "Add task";
  setVal("m_title", task ? task.title : "");
  setVal("m_due", task ? (task.due || "") : "");
  setVal("m_prio", task ? task.priority : "M");
  setVal("m_repeat", task ? (task.repeat || "none") : "none");
  setVal("m_group", task ? (task.group || "") : "");
  setVal("m_notes", task ? (task.notes || "") : "");
  document.getElementById("overlay").classList.add("open");
  document.getElementById("m_title").focus();
}
function closeModal() { document.getElementById("overlay").classList.remove("open"); }

/* ---------- import ---------- */
const AI_IMPORT_PROMPT = `You convert a list of tasks into the import format for the "Tiny Tasklist" app.
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
<PASTE YOUR TASKS HERE>`;

async function copyAiPrompt() {
  try {
    await navigator.clipboard.writeText(AI_IMPORT_PROMPT);
    showToast("AI prompt copied — paste it into an AI with your tasks");
  } catch (e) {
    // Fallback: drop it into the textarea so it's still selectable/copyable.
    document.getElementById("imp_text").value = AI_IMPORT_PROMPT;
    showToast("Copy failed — prompt placed in the box; select & copy it");
  }
}

function openImport() {
  document.getElementById("imp_text").value = "";
  document.getElementById("importOverlay").classList.add("open");
  document.getElementById("imp_text").focus();
}
function closeImport() { document.getElementById("importOverlay").classList.remove("open"); }
async function doImport() {
  const text = document.getElementById("imp_text").value;
  if (!text.trim()) { closeImport(); return; }
  if (LIVE) {
    try {
      const r = await api("POST", "/api/import", { text });
      await loadData();
      closeImport(); render();
      showToast(`Imported ${r.added}` + (r.failed ? ` · ${r.failed} skipped` : ""));
    } catch (e) { showToast("Import failed"); }
  } else {
    // sample mode: accept title-only lines so the demo still does something.
    text.split(/\r?\n/).forEach((line) => {
      const t = line.split("|")[0].trim();
      if (t && !t.startsWith("#")) tasks.push({ id: nextId++, title: t, due: "", priority: "M", repeat: "none", group: "", notes: "", done: false, times: 0 });
    });
    closeImport(); render(); showToast("Imported (sample mode)");
  }
}
async function saveModal() {
  const title = val("m_title").trim();
  if (!title) return;
  const payload = { title, due: val("m_due").trim(), priority: val("m_prio"), repeat: val("m_repeat"), group: val("m_group").trim(), notes: val("m_notes") };
  if (editingId != null) {
    if (LIVE) { try { const u = await api("PATCH", `/api/tasks/${editingId}`, payload); const i = tasks.findIndex((t) => t.id === editingId); if (i >= 0) tasks[i] = u; } catch (e) {} }
    else { const t = tasks.find((x) => x.id === editingId); if (t) { t.title = title; t.due = parseQuickDue(payload.due); t.priority = payload.priority; t.repeat = payload.repeat; t.group = payload.group; t.notes = payload.notes; } }
  } else {
    if (LIVE) { try { tasks.push(await api("POST", "/api/tasks", payload)); } catch (e) {} }
    else { tasks.push({ id: nextId++, title, due: parseQuickDue(payload.due), priority: payload.priority, repeat: payload.repeat, group: payload.group, notes: payload.notes, done: false, times: 0 }); }
  }
  closeModal(); render();
}

/* ---------- misc ---------- */
function escapeHtml(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function setTheme(mode, persist) {
  document.documentElement.setAttribute("data-theme", mode);
  document.getElementById("themeBtn").textContent = mode === "dark" ? "☀️" : "🌙";
  if (persist) { try { localStorage.setItem("tt_theme", mode); } catch (e) {} }
}
function currentTheme() { return document.documentElement.getAttribute("data-theme") || "light"; }
function closeSidebar() { document.getElementById("sidebar").classList.remove("open"); }
function parseQuickDue(s) {
  s = (s || "").trim().toLowerCase();
  if (!s) return "";
  if (s === "today") return isoDate(startOfToday());
  if (s === "tomorrow") return isoDate(addDays(startOfToday(), 1));
  const m = s.match(/^\+(\d+)d$/);
  if (m) return isoDate(addDays(startOfToday(), parseInt(m[1], 10)));
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s;
  return isoDate(startOfToday());
}

/* ---------- init ---------- */
async function init() {
  setTheme(currentTheme(), false);
  document.getElementById("themeBtn").onclick = () => setTheme(currentTheme() === "dark" ? "light" : "dark", true);
  document.getElementById("gearBtn").onclick = (e) => { e.stopPropagation(); const r = e.target.getBoundingClientRect(); popupMenu(r.right - 190, r.bottom + 4, [
    { label: "⬆  Import tasks…", fn: openImport },
    { label: "↺  Reset hazard escalation", fn: resetHazard },
  ]); };
  document.getElementById("search").oninput = (e) => { state.search = e.target.value; render(); };
  document.getElementById("menuBtn").onclick = () => document.getElementById("sidebar").classList.toggle("open");
  document.getElementById("addBtn").onclick = () => openModal(null);
  document.getElementById("m_cancel").onclick = closeModal;
  document.getElementById("m_save").onclick = saveModal;
  document.getElementById("f_time").onchange = (e) => { state.time = e.target.value; saveState(); render(); };
  document.getElementById("f_minprio").onchange = (e) => { state.minPrio = e.target.value; saveState(); render(); };
  document.getElementById("f_group").onclick = () => { state.grouped = !state.grouped; saveState(); render(); };
  document.getElementById("f_collapse").onclick = () => {
    const names = new Set([...document.querySelectorAll(".group-head .gname")].map((e) => e.textContent));
    const anyOpen = [...document.querySelectorAll(".group-head .caret")].some((c) => c.textContent === "▼");
    if (anyOpen) names.forEach((n) => state.collapsed.add(n)); else state.collapsed.clear();
    saveState(); render();
  };
  const overlay = document.getElementById("overlay");
  overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
  const impOverlay = document.getElementById("importOverlay");
  impOverlay.onclick = (e) => { if (e.target === impOverlay) closeImport(); };
  document.getElementById("imp_cancel").onclick = closeImport;
  document.getElementById("imp_go").onclick = doImport;
  document.getElementById("imp_prompt").onclick = copyAiPrompt;
  document.addEventListener("click", closeMenu);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeMenu(); closeModal(); closeImport(); } });
  await loadData();
  render();
}
document.addEventListener("DOMContentLoaded", init);
