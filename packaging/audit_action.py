"""Run ``sluicer audit`` on each page a workflow names, for ``action.yml``.

The action's inputs arrive as environment variables, never written into the
shell script, so a page's address cannot become a command:

- ``URLS``: the pages, one a line or separated by spaces; a ``#`` starts a
  comment line. A path in the workspace is read as a file.
- ``FAIL_ON``: ``error`` (the default) fails the step when a page breaks a
  rule its documentation states, or cannot be read; ``warning`` fails it on
  a warning too; ``never`` only reports.
- ``SITE``: ``false`` leaves each site's robots.txt and llms.txt unread.

Each page is audited by the command itself, so the action says exactly what
``sluicer audit --json`` says. Every error becomes an annotation on the run,
the job's summary gets a table and each error with the rule it breaks, the
answers are kept one JSON line a page in ``RUNNER_TEMP``, and the step's
outputs count them: ``pages``, ``errors``, ``warnings``, ``unreadable`` and
``report``, the path of that file. Standard library only: it runs with the
Python ``uv`` brings, beside the package it calls.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

FAIL_ON = ("error", "warning", "never")


def pages_from(text: str) -> list[str]:
    """The pages ``URLS`` names, in order, without blanks and comments."""
    pages = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        pages.extend(line.split())
    return pages


def findings_in(answer: Any) -> list[dict[str, Any]]:
    """Every finding an audit's JSON holds, wherever it holds it."""
    found = []
    if isinstance(answer, dict):
        if "severity" in answer and "message" in answer:
            found.append(answer)
        for value in answer.values():
            found.extend(findings_in(value))
    elif isinstance(answer, list):
        for value in answer:
            found.extend(findings_in(value))
    return found


def audit(page: str, site: bool) -> dict[str, Any]:
    """What ``sluicer audit --json`` answered for ``page``, with its exit code."""
    command = [sys.executable, "-m", "sluicer", "audit", "--json"]
    if not site:
        command.append("--no-site")
    done = subprocess.run(
        [*command, page], capture_output=True, text=True, encoding="utf-8"
    )
    if done.returncode == 2 or not done.stdout.strip():
        reason = done.stderr.strip().splitlines()[-1:] or ["no answer"]
        return {"page": page, "exit": done.returncode, "unreadable": reason[0]}
    return {"page": page, "exit": done.returncode, "audit": json.loads(done.stdout)}


def _escape(text: str) -> str:
    # What a workflow command's message must not hold as it is.
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> None:
    fail_on = os.environ.get("FAIL_ON", "error").strip() or "error"
    if fail_on not in FAIL_ON:
        print(
            f"fail-on is one of {', '.join(FAIL_ON)}, not {fail_on!r}", file=sys.stderr
        )
        raise SystemExit(2)
    site = os.environ.get("SITE", "true").strip().lower() != "false"
    pages = pages_from(os.environ.get("URLS", ""))
    if not pages:
        print("urls names no page", file=sys.stderr)
        raise SystemExit(2)

    report = Path(os.environ.get("RUNNER_TEMP", ".")) / "sluicer-audit.jsonl"
    rows = ["| page | exit | errors | warnings | records |", "|---|---|---|---|---|"]
    details = []
    errors = warnings = unreadable = 0
    with report.open("w", encoding="utf-8") as answers:
        for page in pages:
            result = audit(page, site)
            answers.write(json.dumps(result) + "\n")
            if "unreadable" in result:
                unreadable += 1
                rows.append(f"| {_cell(page)} | {result['exit']} | | | |")
                details.append(
                    f"- {_cell(page)} could not be read: {result['unreadable']}"
                )
                print(f"::error title=Sluicer audit::{_escape(page)} could not be read")
                continue
            answer = result["audit"]
            errors += answer["errors"]
            warnings += answer["warnings"]
            rows.append(
                f"| {_cell(page)} | {result['exit']} | {answer['errors']} "
                f"| {answer['warnings']} | {len(answer['records'])} |"
            )
            for finding in findings_in(answer):
                if finding["severity"] != "error":
                    continue
                rule = finding.get("rule") or ""
                if finding.get("record") is not None:
                    # Two records of one type say the same message otherwise.
                    finding = {
                        **finding,
                        "message": f"{finding['message']} "
                        f"({finding['source']} record {finding['record']})",
                    }
                details.append(
                    f"- {_cell(page)}: {finding['message']}"
                    + (f" ([rule]({rule}))" if rule else "")
                )
                print(
                    f"::error title=Sluicer audit::{_escape(page)}: "
                    f"{_escape(finding['message'])}"
                )

    summary = ["## Sluicer audit", "", *rows]
    if details:
        summary += ["", "### Errors", "", *details]
    with open(
        os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a", encoding="utf-8"
    ) as out:
        out.write("\n".join(summary) + "\n")
    with open(
        os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8"
    ) as out:
        out.write(
            f"pages={len(pages)}\nerrors={errors}\nwarnings={warnings}\n"
            f"unreadable={unreadable}\nreport={report}\n"
        )
    print(
        f"{len(pages)} pages: {errors} errors, {warnings} warnings, "
        f"{unreadable} could not be read"
    )
    failed = {
        "error": errors or unreadable,
        "warning": errors or warnings or unreadable,
        "never": 0,
    }[fail_on]
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
