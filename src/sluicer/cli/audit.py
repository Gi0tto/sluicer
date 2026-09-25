"""``sluicer audit``: a page's markup held to what Google documents, and its report.

The report is built here, line by line, from the ``Audit`` that
``sluicer.audit`` returns; ``--json`` prints that ``Audit`` as it is.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict

import click

from sluicer.audit import (
    Audit,
    Finding,
    LlmsTxt,
    RecordAudit,
    SiteFile,
    answered_with,
    audit as audit_page,
)
from sluicer.cli.exits import CONTRACT_BROKEN, NOTHING_FOUND
from sluicer.cli.options import _with_fetch_options
from sluicer.cli.output import _kept_line, _moment
from sluicer.cli.source import _read_source
from sluicer.fetch.result import Fetched


@click.command("audit")
@click.argument("source")
@click.option("--json", "as_json", is_flag=True, help="Print the audit as JSON.")
@click.option(
    "--no-site",
    is_flag=True,
    help="Do not read the site's robots.txt and llms.txt for a URL.",
)
@_with_fetch_options
def audit_command(
    source: str,
    as_json: bool,
    no_site: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Check what a page declares against what Google documents, and more.

    For every record JSON-LD, microdata and RDFa declare: the rich-result
    features its type is documented for, the required and recommended
    properties it lacks, and the values in a form the documentation refuses.
    Then what the page lacks -- a title, a description, a canonical, OpenGraph
    -- and where two vocabularies contradict each other. For a URL, also which
    AI agents the site's robots.txt admits and whether its llms.txt keeps to
    llmstxt.org's format; a file or stdin reads no site.

    Exits 3 when anything is an error -- a required property missing, a value
    refused, an llms.txt with no name -- whatever else is true, since that is a
    page breaking a stated rule. Otherwise 1 when no record was declared, since
    there was nothing to audit, and 0. 2, as everywhere, when the page could
    not be read.
    """
    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    site = None
    if fetched is not None and not no_site and fetched.archived is None:
        from sluicer.fetch.site import read_site

        site = read_site(fetched.url, obey_robots=not no_robots)
    result = audit_page(html, url=url, site=site)
    if fetched is not None and fetched.archived is not None and not no_site:
        result.not_checked.insert(
            0,
            "The site's robots.txt and llms.txt: the page is a capture of "
            f"{fetched.archived.captured}, and today's files say nothing of it.",
        )
    if fetched is not None and not 200 <= fetched.status < 300:
        result.not_checked.insert(0, answered_with(fetched.status))
    if as_json:
        payload = asdict(result)
        if fetched is not None:
            payload["fetch"] = {
                "rung": fetched.rung,
                "status": fetched.status,
                "climbs": [asdict(climb) for climb in fetched.climbs],
                **(
                    {"archived": asdict(fetched.archived)}
                    if fetched.archived is not None
                    else {}
                ),
                **(
                    {"cached": asdict(fetched.cached)}
                    if fetched.cached is not None
                    else {}
                ),
            }
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        shown = "standard input" if source == "-" else (url or source)
        click.echo(_audit_report(shown, result, fetched, not no_robots, no_site))
    if result.errors:
        raise SystemExit(CONTRACT_BROKEN)
    if not result.records:
        raise SystemExit(NOTHING_FOUND)


# Findings a feature's own line already reports, as its missing properties.
_SUMMED = frozenset({"missing-required", "missing-recommended", "incomplete-part"})


def _audit_report(
    shown: str,
    result: Audit,
    fetched: Fetched | None,
    obeyed_robots: bool,
    no_site: bool,
) -> str:
    """The report ``audit`` prints, deterministic for a given page and site."""
    lines = [f"page      {shown}"]
    if fetched is not None:
        lines.append(
            f"fetch     {fetched.rung} rung, status {fetched.status}, "
            f"{fetched.seconds:.2f} s"
        )
        if fetched.cached is not None:
            lines.append(f"cached    {_kept_line(fetched.cached)}")
        if fetched.archived is not None:
            capture = fetched.archived
            lines.append(
                f"archived  {capture.archive} capture of {capture.url} at "
                f"{_moment(capture.captured)}, asked for {_moment(capture.asked)}"
            )
        whose = (
            f"{fetched.archived.archive}'s"
            if fetched.archived is not None
            else "the site's"
        )
        lines.append(
            f"robots    allowed by {whose} robots.txt"
            if obeyed_robots
            else "robots    not asked (--no-robots)"
        )
    lines.append("")
    by_source: dict[str, int] = {}
    for record in result.records:
        by_source[record.source] = by_source.get(record.source, 0) + 1
    counted = ", ".join(f"{name} {n}" for name, n in by_source.items())
    records = len(result.records)
    lines.append(
        f"records   {records} audited"
        + (f" ({counted})" if counted else ", none declared")
    )
    for record in result.records:
        lines.extend(_record_lines(record))
    lines.append("")
    lines.append(f"page      {_counted(len(result.page), 'finding')}")
    lines.extend(_finding_line(finding) for finding in result.page)
    if result.robots_txt is not None:
        lines.append("")
        lines.extend(_agent_lines(result, result.robots_txt))
    if result.llms_txt is not None and result.llms_full_txt is not None:
        lines.append("")
        lines.extend(_llms_lines("llms.txt", result.llms_txt))
        lines.extend(_llms_lines("llms-full", result.llms_full_txt))
    if result.tdm is not None:
        said = "reserved" if result.tdm.reserved else "not reserved"
        policy = f", policy {result.tdm.policy}" if result.tdm.policy else ""
        lines.append(
            f"tdm       text and data mining {said} "
            f"(TDMRep, by its {result.tdm.source}{policy})"
        )
    notes = list(result.not_checked)
    if fetched is None and not no_site:
        notes = [
            note.replace("the site was not read.", "the site is read only for a URL.")
            for note in notes
        ]
    elif no_site:
        notes = [
            note.replace("the site was not read.", "not asked (--no-site).")
            for note in notes
        ]
    if notes:
        lines.append("")
        lines.append("not checked")
        lines.extend(f"  {note}" for note in notes)
    lines.append("")
    lines.append(
        f"summary   {_counted(result.errors, 'error')}, "
        f"{_counted(result.warnings, 'warning')}, {_counted(result.notes, 'note')}"
    )
    return "\n".join(lines)


def _counted(n: int, what: str) -> str:
    return f"{n} {what}{'s' if n != 1 else ''}"


def _record_lines(record: RecordAudit) -> list[str]:
    kind = " / ".join(record.types) or "no type"
    lines = [f"  {kind}  ({record.source} record {record.index})"]
    if not record.features:
        lines.append("    no rich-result feature is documented for this type")
    width = max((len(feature.name) for feature in record.features), default=0)
    for feature in record.features:
        if feature.requirements_met is None:
            verdict = f"retired: {feature.note}"
        elif feature.missing_required:
            missing = feature.missing_required
            verdict = f"{len(missing)} required missing: {_collapsed(missing)}"
        elif feature.requirements_met:
            verdict = "requirements met"
        else:
            verdict = "a value this feature refuses"
        if feature.status == "limited":
            verdict += "  (limited: see the note in --json)"
        lines.append(f"    {feature.name:{width}}  {verdict}")
        if feature.missing_recommended:
            lines.append(
                f"    {'':{width}}  recommended, missing: "
                + _collapsed(feature.missing_recommended)
            )
        if feature.incomplete_parts:
            lines.append(
                f"    {'':{width}}  optional parts unusable, missing: "
                + _collapsed(feature.incomplete_parts)
            )
    for name in record.not_checked:
        lines.append(f"    not checked here: {name}")
    lines.extend(
        "  " + _finding_line(finding)
        for finding in record.findings
        if finding.code not in _SUMMED
    )
    return lines


def _collapsed(paths: list[str]) -> str:
    """Paths with their list positions folded: twenty reviews lacking a date are
    one entry, ``review[].datePublished (20)``. ``--json`` keeps every one."""
    counted: dict[str, int] = {}
    for path in paths:
        folded = re.sub(r"\[[0-9]+\]", "[]", path)
        counted[folded] = counted.get(folded, 0) + 1
    return ", ".join(path + (f" ({n})" if n > 1 else "") for path, n in counted.items())


def _finding_line(finding: Finding) -> str:
    where = (
        f"{finding.path}: "
        if finding.path and finding.path not in finding.message
        else ""
    )
    rule = f"  [{finding.rule}]" if finding.rule else ""
    return f"  {finding.severity:7}  {where}{finding.message}{rule}"


def _agent_lines(result: Audit, robots: SiteFile) -> list[str]:
    if robots.status is not None:
        state = f"status {robots.status}"
        if 400 <= robots.status < 500:
            state += ", none published: everything is allowed"
    else:
        state = f"not read: {robots.error}"
    lines = [f"agents    robots.txt {robots.url}, {state}"]
    token = max((len(verdict.agent) for verdict in result.crawlers), default=0)
    vendor = max((len(verdict.vendor) for verdict in result.crawlers), default=0)
    for verdict in result.crawlers:
        allowed = {True: "allowed", False: "disallowed", None: "unknown"}[
            verdict.allowed
        ]
        group = f"User-agent: {verdict.group}" if verdict.group else "no group applies"
        caveat = "  (may ignore robots.txt)" if verdict.honours_robots is False else ""
        lines.append(
            f"  {verdict.agent:{token}}  {verdict.vendor:{vendor}}  "
            f"{verdict.use:8}  {allowed:10}  {group}{caveat}"
        )
    # A group states its preferences for every agent it decides for, so they
    # are said once per group, not once per agent.
    stated: dict[str, list[str]] = {}
    for verdict in result.crawlers:
        for label, said in (
            ("content-usage", verdict.content_usage),
            ("content-signal", verdict.content_signal),
        ):
            if said and verdict.group is not None:
                line = f"{label} " + ", ".join(f"{k}={v}" for k, v in said.items())
                if line not in stated.setdefault(verdict.group, []):
                    stated[verdict.group].append(line)
    for group, statements in stated.items():
        for line in statements:
            lines.append(f"          User-agent: {group} states {line}")
    if result.other_agents:
        lines.append(
            "          also named, by no agent documented here: "
            + ", ".join(result.other_agents)
        )
    return lines


def _llms_lines(label: str, llms: LlmsTxt) -> list[str]:
    if not llms.present:
        answered = f"status {llms.status}" if llms.status is not None else "no answer"
        lines = [f"{label:9} {llms.url}: not served ({answered})"]
    elif label == "llms.txt":
        described = f'"{llms.name}"' if llms.name else "no name"
        lines = [
            f"{label:9} {llms.url}: {described}, "
            f"{_counted(len(llms.sections), 'section')}, {_counted(llms.links, 'link')}"
        ]
    else:
        lines = [f"{label:9} {llms.url}: {llms.length:,} characters"]
    lines.extend(_finding_line(finding) for finding in llms.findings)
    return lines
