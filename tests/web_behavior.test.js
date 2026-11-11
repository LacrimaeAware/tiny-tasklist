const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");

function app(protocol = "http:", search = "") {
  const elements = new Map();
  const context = vm.createContext({
    window: { location: { protocol, search }, confirm: () => true },
    URLSearchParams,
    localStorage: { getItem: () => null, setItem: () => {} },
    document: {
      addEventListener() {},
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, { value: "", hidden: true, disabled: false, textContent: "" });
        return elements.get(id);
      },
    },
    SAMPLE_TASKS: [{ id: 1, title: "Sample", due: "", priority: "M" }],
    fetch: async () => { throw new Error("offline"); },
    messages: [], closed: false, renders: 0,
  });
  vm.runInContext(source, context);
  vm.runInContext(`
    render = () => { renders++; };
    showToast = (message) => messages.push(message);
    closeModal = () => { closed = true; };
    closeImport = () => { closed = true; };
  `, context);
  const run = (code) => vm.runInContext(code, context);
  return { context, elements, run };
}

test("new visitors can see undated tasks", () => {
  const { run } = app();
  assert.equal(run("state.time"), "any");
  assert.equal(run("timePass({due: ''}, state.category, state.time)"), true);
});

test("All includes completed and suspended tasks but excludes deleted tasks", () => {
  const { run } = app();
  assert.equal(run("categoryPass({done: true}, 'all')"), true);
  assert.equal(run("categoryPass({suspended: true}, 'all')"), true);
  assert.equal(run("categoryPass({is_deleted: true}, 'all')"), false);
  assert.equal(run("categoryPass({done: true}, 'active')"), false);
});

test("a live connection failure never replaces tasks with demo data", async () => {
  const { run } = app();
  run("tasks = [{id: 99, title: 'Stored task'}]");
  await assert.rejects(run("loadData()"), /Could not reach the local server/);
  assert.equal(run("LIVE"), true);
  assert.equal(run("tasks[0].id"), 99);
});

test("opening a file uses the in-memory demo without a server request", async () => {
  const { run } = app("file:");
  await run("loadData()");
  assert.equal(run("LIVE"), false);
  assert.equal(run("tasks[0].title"), "Sample");
  assert.throws(() => run("parseQuickDue('next week')"), /In the demo/);
  assert.throws(() => run("parseQuickDue('2026-02-30')"), /In the demo/);
  assert.equal(run("parseQuickDue('2026-02-28')"), "2026-02-28");
});

test("the explicit hosted demo never requests or saves server data", async () => {
  const { context, run } = app("http:", "?demo=1");
  context.fetch = async () => { throw new Error("The demo must not call the API"); };
  await run("loadData()");
  assert.equal(run("LIVE"), false);
  assert.equal(run("tasks[0].title"), "Sample");
  run("document.getElementById('m_title').value = 'In-memory example'");
  await run("saveModal()");
  assert.equal(run("tasks[1].title"), "In-memory example");
  assert.equal(context.closed, true);
  assert.equal(run("LIVE"), false);
});

test("a rejected save keeps the form and entered text", async () => {
  const { context, run, elements } = app();
  context.fetch = async () => ({ ok: false, status: 400, json: async () => ({ error: "Invalid due date" }) });
  run("document.getElementById('m_title').value = 'Keep this draft'; document.getElementById('m_due').value = 'bad date'");
  await run("saveModal()");
  assert.equal(context.closed, false);
  assert.equal(elements.get("m_title").value, "Keep this draft");
  assert.equal(elements.get("m_due").value, "bad date");
  assert.equal(elements.get("m_error").hidden, false);
  assert.match(elements.get("m_error").textContent, /Invalid due date/);
  assert.equal(elements.get("m_save").disabled, false);
  assert.equal(run("tasks.length"), 0);
});

test("a successful save uses the stored task and closes the form", async () => {
  const { context, run } = app();
  context.fetch = async () => ({ ok: true, json: async () => ({ id: 8, title: "Saved task" }) });
  run("document.getElementById('m_title').value = 'Saved task'");
  await run("saveModal()");
  assert.equal(context.closed, true);
  assert.equal(run("tasks[0].id"), 8);
});

test("failed mutations leave the visible task unchanged and report failure", async () => {
  for (const action of ["toggleDone(task)", "setSuspended(task, true)", "deleteTask(task)", "restoreTask(task)", "hardDelete(task)"]) {
    const { context, run } = app();
    run("var task = {id: 7, title: 'Stored task', done: false, suspended: false, is_deleted: false}; tasks = [task]");
    const before = run("JSON.stringify(tasks)");
    await run(action);
    assert.equal(run("JSON.stringify(tasks)"), before, action);
    assert.match(context.messages[0], /Could not/, action);
    assert.equal(context.renders, 0, action);
  }
});

test("partial imports retain only skipped lines for a corrected retry", async () => {
  const { context, run, elements } = app();
  context.fetch = async (url) => ({
    ok: true,
    json: async () => url === "/api/import"
      ? { added: 1, failed: 1, details: ["Line 2: Invalid due date"] }
      : { tasks: [{ id: 3, title: "Added" }] },
  });
  run("document.getElementById('imp_text').value = 'Added\\nNeeds correction | due: bad'");
  await run("doImport()");
  assert.equal(context.closed, false);
  assert.equal(elements.get("imp_text").value, "Needs correction | due: bad");
  assert.match(elements.get("imp_result").textContent, /Added 1.*Invalid due date/);
  assert.equal(elements.get("imp_result").hidden, false);
  assert.equal(run("tasks[0].id"), 3);
});
