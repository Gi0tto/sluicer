// Types for the answers the Python package gives, as `dataclasses.asdict`
// writes them: the same field names, in snake_case, as `sluicer extract`
// prints. Written by hand from sluicer's dataclasses; the tests hold the
// answers themselves to the native package's.

import type { PyodideAPI } from "pyodide";

/** A page: text, or its bytes, which let Sluicer honour the page's charset. */
export type Page = string | Uint8Array | ArrayBuffer;

/** A JSON value as a page declared it. Numbers are kept as their text. */
export type JsonValue =
  | string
  | null
  | boolean
  | JsonValue[]
  | { [key: string]: JsonValue };

/** One summary answer, and exactly where it was read. */
export interface SummaryField {
  value: string;
  /** The reader: "jsonld", "microdata", "opengraph", "html", ... */
  source: string;
  /** What was read: "Product.offers.price", "og:title", "<title>". */
  key: string;
  /** An XPath, with a JSON pointer after "#" inside a JSON-LD block. */
  where: string | null;
}

/** A question the page answers in two ways that mean different things. */
export interface Conflict {
  question: string;
  /** The summary's answer first, then every other. */
  answers: SummaryField[];
}

/** One property of a record, with the reader that declared it. */
export interface Field {
  value: JsonValue;
  source: string;
  where: string | null;
}

/** One thing the page declares, and every property it declares of it. */
export interface Record {
  type: string | null;
  types: string[];
  fields: { [name: string]: Field };
  /** "induced" for a row induction found; null for the page-level record. */
  source: string | null;
  where: string | null;
}

export interface Links {
  canonical?: string;
  canonical_conflict?: string[];
  alternates?: { hreflang: string; href: string }[];
  feeds?: { format: string; href: string; title: string }[];
  next?: string;
  prev?: string;
  amphtml?: string;
  oembed?: string[];
  manifest?: string;
}

export interface HeaderRights {
  robots?: string[];
  agents?: { [agent: string]: string[] };
  tdm_reservation?: string;
  tdm_policy?: string;
  content_usage?: { [key: string]: string };
}

export interface Rights {
  robots?: string[];
  agents?: { [agent: string]: string[] };
  tdm_reservation?: string;
  tdm_policy?: string;
  license?: string[];
  http?: HeaderRights;
}

/** A guess from what the page shows, never a declaration. */
export interface Guess {
  value: string;
  where: string;
  rule: string;
}

/** What Sluicer found in one page, as Python's `sluicer.Extraction`. */
export interface Extraction {
  url: string | null;
  summary: { [question: string]: SummaryField };
  normalised: { [question: string]: string };
  conflicts: Conflict[];
  records: Record[];
  sources: string[];
  links: Links;
  rights: Rights;
  /** The guesses read off the visible page; empty when `visible: false` was asked for. */
  visible: { [question: string]: Guess };
}

export interface ExtractOptions {
  /** The address the page came from, to resolve its links. Never fetched. */
  url?: string;
  /** Also read the rows a page repeats when it declares nothing about them. */
  induce?: boolean;
  /** Also guess the title, byline and dates the page shows, never in the summary. On by default; `false` reads what the page declares alone. */
  visible?: boolean;
  /** The response's headers, when the page came over HTTP. */
  headers?: { [name: string]: string };
}

/** An extractor, as the JSON file `sluicer compile` writes. */
export interface Extractor {
  format: number;
  sluicer: string;
  learnt_from: string[];
  summary: { [question: string]: string | null };
  types: string[];
  listing: null | {
    container: string;
    member: string;
    rows: number[];
    empty: number;
    /**
     * For each step of `container`, how many elements matched it on every
     * page learnt, or null where they differed. Absent before 0.7.1.
     */
    siblings?: (number | null)[];
    chosen?: boolean;
    fields: {
      name: string;
      path: string;
      missing: number;
      shape: string | null;
      reads: string | null;
      samples: string[];
    }[];
  };
  notes: string[];
  fields?: {
    name: string;
    path: string;
    shape: string | null;
    reads: string | null;
    samples: string[];
    anchor?: { label: string; kind: string };
  }[];
  /** An extractor written by selectors (`compile` with `select`). */
  select?: {
    /** The selector of a listing's rows, or null for one value per page. */
    rows: string | null;
    empty?: number;
    fields: {
      name: string;
      selector: string;
      missing?: number;
      shape: string | null;
      reads: string | null;
      samples: string[];
      first: boolean;
    }[];
  };
}

export interface Check {
  name: string;
  expected: string;
  got: string;
  ok: boolean;
}

/** An extractor replayed on one page. `ok` is false when any check failed. */
export interface Run {
  url: string | null;
  ok: boolean;
  rows: { [field: string]: string }[];
  summary: { [question: string]: string };
  checks: Check[];
  fields: { [name: string]: string };
}

export interface CompileOptions {
  /** Learn the listing the pages repeat: true always, false never. */
  listing?: boolean;
  /** Example values, by the name each is to have. */
  want?: { [name: string]: string };
  /** What to call each page in `learnt_from`; its address by default. */
  names?: string[];
  /**
   * Fields written by selector instead of learnt, by name: `{ price:
   * "span.price::text" }`, CSS or XPath. Not with `want` or `listing`. With
   * no page given, the selectors are all the extractor holds a page to.
   */
  select?: { [name: string]: string };
  /** With `select`, the selector of a listing's rows: `"li.product"`. */
  rows?: string;
}

/**
 * Every call takes only the options it names: one it does not know, a
 * misspelt `induce` or another call's option, is a TypeError that names it.
 */
export interface Sluicer {
  /** The Python package's version, which is this npm package's. */
  readonly version: string;
  readonly python: string;
  readonly lxml: string;
  /** Whether the markdown extra was installed. */
  readonly markdown: boolean;
  /** The Pyodide instance Sluicer runs in. */
  readonly pyodide: PyodideAPI;
  extract(html: Page, options?: ExtractOptions): Extraction;
  /** Needs `createSluicer({ markdown: true })`. */
  toMarkdown(html: Page, options?: { url?: string }): string;
  compile(
    pages: { html: Page; url?: string | null }[],
    options?: CompileOptions,
  ): Extractor;
  run(extractor: Extractor | string, html: Page, options?: { url?: string }): Run;
}

export interface CreateOptions {
  /**
   * Also install the markdown extra (trafilatura) from PyPI, for
   * `toMarkdown`. Adds about three seconds and 14 MB of downloads to every
   * start: Pyodide's cache keeps its own packages, not PyPI's.
   */
  markdown?: boolean;
  /** Where Pyodide keeps the packages it downloads. Node only. */
  packageCacheDir?: string;
  /** A Pyodide instance of your own, of the pinned version, to install into. */
  pyodide?: PyodideAPI;
}

export class SluicerError extends Error {
  /**
   * The Python exception's name: "NothingToLearn", "ValueError", ... Or the
   * package's own: "MarkdownExtraMissing", and "PackageNotLoaded" when
   * createSluicer could not load a package Sluicer needs into Pyodide.
   */
  readonly type: string;
  constructor(type: string, message: string);
}

export function createSluicer(options?: CreateOptions): Promise<Sluicer>;
