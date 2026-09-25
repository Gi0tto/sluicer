// Runs Sluicer in this browser: Pyodide from jsDelivr, the wheel of the
// commit this site was built from, and the bridge the npm package calls
// into, so the answers are the Python package's own. A pasted page stays in
// this page's memory: it is handed to Python as a string and never rendered,
// and the Content-Security-Policy lets the page connect to nothing but this
// site and the CDN. The files beside this one are added by
// scripts/docs_try.py when the site is built.

const $ = (id) => document.getElementById(id);
const status = $("status");
// pyodide.js is loaded by the page, pinned and checked by its integrity; its
// own files come from the same folder of the CDN.
const INDEX = document
  .querySelector('script[src*="pyodide.js"]')
  .src.replace(/pyodide\.js$/, "");

let bridge = null;
// Fetched while Python starts, so that once it is ready the page makes no
// request at all, whatever is clicked.
let examplePage = "";

function say(state, text) {
  status.dataset.state = state;
  status.textContent = text;
}

async function start() {
  const wheel = await (await fetch("wheel.json")).json();
  examplePage = await (await fetch("example.html")).text();
  const pyodide = await globalThis.loadPyodide({
    indexURL: INDEX,
    stdout() {},
    stderr() {},
  });
  say("loading", "Installing lxml and Sluicer…");
  await pyodide.loadPackage(
    wheel.requires.map((r) => r.match(/^[A-Za-z0-9._-]+/)[0]),
    { messageCallback() {}, errorCallback() {} },
  );
  const site = pyodide.runPython(
    "import sysconfig; sysconfig.get_paths()['purelib']",
  );
  const whl = await (await fetch(wheel.file)).arrayBuffer();
  pyodide.unpackArchive(whl, "wheel", { extractDir: site });
  const globals = pyodide.toPy({});
  pyodide.runPython(await (await fetch("bridge.py")).text(), { globals });
  bridge = globals;
  const about = JSON.parse(bridge.get("about")());
  $("version").textContent = `version ${about.sluicer}, with Python ${about.python} and lxml ${about.lxml}`;
  const took = performance.now();
  status.dataset.readyMs = took.toFixed(0);
  say("ready", `Ready in ${(took / 1000).toFixed(1)} s. Sluicer ${about.sluicer} runs in this tab.`);
  $("run").disabled = false;
}

function extract(event) {
  event.preventDefault();
  if (!bridge) return;
  const options = {
    url: $("url").value.trim() || null,
    induce: $("induce").checked,
    visible: $("visible").checked,
  };
  const answer = JSON.parse(
    bridge.get("extract")($("html").value, JSON.stringify(options)),
  );
  $("result").hidden = Boolean(answer.error);
  $("failed").hidden = !answer.error;
  if (answer.error) {
    $("error").textContent = `${answer.error.type}: ${answer.error.message}`;
    return;
  }
  show(answer.ok);
}

function show(found) {
  const rows = Object.entries(found.summary).filter(([, field]) => field);
  const body = $("summary").tBodies[0];
  body.replaceChildren(
    ...rows.map(([question, field]) => {
      const row = document.createElement("tr");
      const conflict = found.conflicts.find((c) => c.question === question);
      const answer = conflict
        ? `${field.value}  (also ${conflict.answers.slice(1).map((a) => `${a.value} in ${a.source}`).join(", ")})`
        : field.value;
      for (const text of [question, answer, `${field.source}: ${field.key}`]) {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.append(cell);
      }
      if (conflict) row.className = "conflict";
      return row;
    }),
  );
  const records = found.records.length;
  $("said").textContent =
    `${rows.length} answers, ${records} record${records === 1 ? "" : "s"}, ` +
    `read by ${found.sources.length ? found.sources.join(", ") : "no reader"}` +
    (found.conflicts.length ? `; ${found.conflicts.length} question answered two ways, marked.` : ".");
  $("json").textContent = JSON.stringify(found, null, 2);
}

function example() {
  $("html").value = examplePage;
  $("url").value = "https://example.com/p/bp-2210";
}

async function copy() {
  await navigator.clipboard.writeText($("json").textContent);
  $("copy").textContent = "Copied";
  setTimeout(() => ($("copy").textContent = "Copy"), 1500);
}

$("form").addEventListener("submit", extract);
$("example").addEventListener("click", example);
$("copy").addEventListener("click", copy);
start().catch((error) => {
  say("failed", `Python could not start in this browser: ${error.message}`);
  console.error(error);
});
