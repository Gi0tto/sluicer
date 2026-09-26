# In GitHub Actions

`action.yml` at the repository's root is a GitHub Action that runs
[`sluicer audit`](audit.md) on the pages you name, so a pull request that
breaks a page's structured data fails its checks, with each rule it breaks
linked to the documentation that states it.

```yaml
jobs:
  structured-data:
    runs-on: ubuntu-latest
    steps:
      - uses: Gi0tto/sluicer@v0.10.0
        with:
          urls: |
            https://staging.example.com/
            https://staging.example.com/products/brake-pads
```

Pin it as you pin any action you did not write: by the commit a tag points
to, `Gi0tto/sluicer@<commit> # v0.10.0`, since a tag can be moved.

## Inputs

| input | default | what it does |
|---|---|---|
| `urls` | required | The pages, one a line or separated by spaces; a line starting with `#` is a comment. A path in the workspace is read as a file, so a site built earlier in the job can be audited without serving it. |
| `fail-on` | `error` | `error` fails the step when a page breaks a rule its documentation states, or cannot be read. `warning` fails it on a warning too. `never` only reports. |
| `site` | `true` | Also read each site's robots.txt and llms.txt: which AI agents it admits, and whether its llms.txt keeps to llmstxt.org's format. `false` reads the pages alone. |
| `version` | this release's | The Sluicer release it installs from PyPI, with no extra: the base install fetches over HTTP. |
| `package` | empty | What to install instead, as uv's `--with` takes it; `.` in a checkout of Sluicer is how this repository tests the action. |

The action installs uv and runs Sluicer with the Python uv brings, so the job
needs no Python of its own. Every input reaches the script through its
environment, never written into a shell command, so an address cannot become
one.

## What it reports

- The step fails, or not, as `fail-on` says. A page that declares no record is
  not a failure: `sluicer audit` exits 1 for it, and there is nothing to check.
- Each error is an annotation on the run, naming the page, the record and the
  rule.
- The job's summary holds a table, one row a page with its exit code, errors,
  warnings and records, and then each error with a link to its rule.
- Outputs, for the steps after it: `pages`, `errors`, `warnings`,
  `unreadable`, and `report`, the path of a file holding each page's
  `sluicer audit --json`, one JSON line a page.

```yaml
      - id: audit
        uses: Gi0tto/sluicer@v0.10.0
        with:
          urls: https://staging.example.com/
          fail-on: never
      - env:
          ERRORS: ${{ steps.audit.outputs.errors }}
        run: echo "$ERRORS errors"
```

## How it is tested

The workflow `.github/workflows/github-action.yml` uses the action as a
workflow of yours would, with `uses: ./`, on pages its own job serves on the
runner's loopback: the examples' made-up article, which breaks no rule, and
the brake pads' page, whose products lack properties Google requires. It
checks that the first passes, that the second fails the step, that
`fail-on: never` reports the same errors without failing, and that the
report is JSON. The suite runs the script the action calls on the same pages
as files, and on a page that cannot be read.
