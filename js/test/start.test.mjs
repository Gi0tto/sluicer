// createSluicer when Pyodide cannot load a package Sluicer needs. loadPackage
// does not throw when a download fails: it logs and resolves, and before this
// the first call failed later on "No module named 'lxml'" (Node 18 in CI).
// The loader here is a fake, so nothing is downloaded to make it fail.
import assert from "node:assert/strict";
import { test } from "node:test";
import { loadPyodide } from "pyodide";
import { SluicerError, createSluicer } from "../index.js";

// A Pyodide of the pinned version whose loadPackage is `load`.
async function pyodideLoading(load) {
  const real = await loadPyodide({ stdout() {}, stderr() {} });
  const loadPackage = real.loadPackage.bind(real);
  return new Proxy(real, {
    get(target, name) {
      if (name === "loadPackage") {
        return (names, options) => load(loadPackage, names, options);
      }
      const value = Reflect.get(target, name);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

test("a package that never loads is an error naming it, where from, and what to do", async () => {
  const asked = [];
  const pyodide = await pyodideLoading(async (_, names, options) => {
    asked.push([...names].sort());
    // What Pyodide reports when the request for a wheel fails.
    options.errorCallback("The following error occurred while loading lxml:");
    options.errorCallback("Failed to load 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/lxml.whl': request failed.");
    return [];
  });

  await assert.rejects(createSluicer({ pyodide }), (error) => {
    assert.ok(error instanceof SluicerError, error);
    assert.equal(error.type, "PackageNotLoaded");
    assert.match(error.message, /could not load click, cssselect, lxml into Pyodide, tried twice/);
    assert.match(error.message, /https:\/\/cdn\.jsdelivr\.net\/pyodide\/v314\.0\.7\/full\//);
    assert.match(error.message, /request failed/);
    assert.match(error.message, /reach cdn\.jsdelivr\.net/);
    return true;
  });
  // Asked once for everything, and once more for what did not import.
  assert.deepEqual(asked, [
    ["click", "cssselect", "lxml"],
    ["click", "cssselect", "lxml"],
  ]);
});

test("a package that fails once is downloaded again, and Sluicer starts", async () => {
  const asked = [];
  const pyodide = await pyodideLoading(async (loadPackage, names, options) => {
    asked.push([...names].sort());
    if (asked.length === 1) {
      options.errorCallback("The following error occurred while loading lxml:");
      return loadPackage(names.filter((name) => name !== "lxml"), options);
    }
    return loadPackage(names, options);
  });

  const sluicer = await createSluicer({ pyodide });

  assert.deepEqual(asked, [["click", "cssselect", "lxml"], ["lxml"]]);
  assert.equal(sluicer.extract("<title>Één</title>").summary.title.value, "Één");
});
