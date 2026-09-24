// What the tests share: where the checkout is, and the native answers.
import { readdir, readFile } from "node:fs/promises";

export const ROOT = new URL("../../", import.meta.url);

/** Every native answer of one kind, as scripts/expected.py wrote it. */
export async function expected(kind) {
  const folder = new URL(`test/expected/${kind}/`, new URL("../", import.meta.url));
  const names = (await readdir(folder)).filter((n) => n.endsWith(".json")).sort();
  return Promise.all(
    names.map(async (name) => ({
      name: name.replace(/\.json$/, ""),
      ...JSON.parse(await readFile(new URL(name, folder), "utf8")),
    })),
  );
}

/** A page of the checkout, as its bytes or as text. */
export async function page(path, as = "bytes") {
  const bytes = await readFile(new URL(path, ROOT));
  return as === "text" ? bytes.toString("utf8") : bytes;
}
