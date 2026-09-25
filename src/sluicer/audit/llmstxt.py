"""Read a site's llms.txt against the format llmstxt.org defines.

The proposal (v2, August 2026, read at https://llmstxt.org/ on 2026-09-23)
asks for, in order: an optional byte-order mark; an H1 with the name of the
project or site, "the only required section"; a blockquote with a short
summary; any markdown that is not a heading; then sections under H2 headings,
each a "file list" whose items are a markdown link ``[name](url)``, optionally
followed by ``:`` and notes. That is what is checked, line by line, with no
markdown library: a missing H1 is an error, every other departure a warning.

``llms-full.txt`` is not part of the proposal, which defines no format for
it, so only whether a site serves one, and how long it is, is reported.

Google said in June 2026 that these files are not used by Google Search and
neither help nor harm a page there (Search Central changelog); they are for
the agents and tools that read them.
"""

from __future__ import annotations

import re

from sluicer.audit.report import Finding, LlmsSection, LlmsTxt, SiteFile

SPEC = "https://llmstxt.org/"

_SETEXT_H1 = re.compile(r"^=+[ \t]*$")
_ITEM = re.compile(r"^[ \t]{0,3}(?:[-*+]|[0-9]+[.)])[ \t]+(.*)$")
_LINK = re.compile(
    r"^\[(?P<name>[^\]]+)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    r"(?:\s*:\s*(?P<notes>.*))?$"
)
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_HTML = re.compile(r"^\s*<(?:!doctype\s+html|html[\s>]|head[\s>]|body[\s>])", re.I)


def _atx(line: str) -> tuple[str, str | None] | None:
    """An ATX heading's marks and its text, or None for a line that is none.

    The text is what follows the marks and a space or tab, without the
    closing ``#`` marks and the spaces and tabs around them; None where
    nothing follows the marks, and a line of more than six marks and nothing
    else is an H6 with none. Read by hand: as a pattern -- the text lazily,
    then spaces, marks and spaces to the end -- a line that ended in anything
    else was tried at every split of it, and "# a", four thousand spaces and
    a "b" took a minute.
    """
    rest = line.lstrip("#")
    marks = len(line) - len(rest)
    if not marks:
        return None
    if marks > 6 or rest[:1] not in (" ", "\t"):
        return ("#" * min(marks, 6), None) if not rest.strip(" \t") else None
    return line[:marks], rest.lstrip(" \t").rstrip(" \t").rstrip("#").rstrip(" \t")


def read_llms_txt(file: SiteFile) -> LlmsTxt:
    """What ``file``, a site's llms.txt, holds and gets wrong."""
    if not file.found or file.text is None:
        return LlmsTxt(url=file.url, status=file.status, present=False)
    text = file.text.lstrip("\ufeff")
    report = _Reading(file.url)
    if _HTML.match(text):
        report.error(
            "llms-html",
            "the site answers with an HTML page, not a markdown llms.txt",
        )
        return report.done(file, text)
    lines = text.splitlines()
    position = _skip_blank(lines, 0)
    position = report.name_from(lines, position)
    position = report.summary_from(lines, _skip_blank(lines, position))
    report.body_from(lines, position)
    if not report.sections:
        report.findings.append(
            _finding(
                "info",
                "llms-no-file-list",
                "no H2 section lists files, so the file links nothing for an "
                "agent to follow",
                "",
            )
        )
    return report.done(file, text)


def read_llms_full_txt(file: SiteFile) -> LlmsTxt:
    """Whether the site serves an llms-full.txt, and how long it is."""
    if not file.found or file.text is None:
        return LlmsTxt(url=file.url, status=file.status, present=False)
    findings = []
    if _HTML.match(file.text.lstrip("\ufeff")):
        findings.append(
            _finding(
                "error",
                "llms-html",
                "the site answers with an HTML page, not a text file",
                "",
            )
        )
    return LlmsTxt(
        url=file.url,
        status=file.status,
        present=True,
        length=len(file.text),
        findings=findings,
    )


def _skip_blank(lines: list[str], position: int) -> int:
    while position < len(lines) and not lines[position].strip():
        position += 1
    return position


def _finding(severity: str, code: str, message: str, path: str) -> Finding:
    return Finding(
        severity=severity,
        code=code,
        message=message,
        source="llms.txt",
        path=path,
        rule=SPEC,
    )


class _Reading:
    """One llms.txt, read top to bottom."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.name: str | None = None
        self.summary: str | None = None
        self.sections: list[LlmsSection] = []
        self.findings: list[Finding] = []

    def error(self, code: str, message: str, path: str = "") -> None:
        self.findings.append(_finding("error", code, message, path))

    def warning(self, code: str, message: str, path: str = "") -> None:
        self.findings.append(_finding("warning", code, message, path))

    def done(self, file: SiteFile, text: str) -> LlmsTxt:
        return LlmsTxt(
            url=file.url,
            status=file.status,
            present=True,
            name=self.name,
            summary=self.summary,
            sections=self.sections,
            links=sum(section.links for section in self.sections),
            length=len(text),
            findings=self.findings,
        )

    def name_from(self, lines: list[str], position: int) -> int:
        """The H1 the file must open with; where reading goes on from."""
        if position < len(lines):
            heading = _atx(lines[position])
            if heading and len(heading[0]) == 1 and heading[1]:
                self.name = heading[1].strip()
                return position + 1
            following = lines[position + 1] if position + 1 < len(lines) else ""
            if lines[position].strip() and _SETEXT_H1.match(following):
                self.name = lines[position].strip()
                return position + 2
        self.error(
            "llms-no-name",
            "the file does not open with an H1 naming the site, the one section "
            "llmstxt.org requires",
            "line " + str(position + 1),
        )
        return position

    def summary_from(self, lines: list[str], position: int) -> int:
        quoted: list[str] = []
        while position < len(lines) and lines[position].lstrip().startswith(">"):
            quoted.append(lines[position].lstrip()[1:].strip())
            position += 1
        if quoted and any(quoted):
            self.summary = " ".join(part for part in quoted if part)
        else:
            self.warning(
                "llms-no-summary",
                "no blockquote summary follows the name",
                "line " + str(position + 1),
            )
        return position

    def body_from(self, lines: list[str], position: int) -> None:
        """The details, then the H2 file lists, until the end."""
        section: str | None = None
        links = items = strays = 0
        fenced: str | None = None
        for number in range(position, len(lines)):
            line = lines[number]
            fence = _FENCE.match(line)
            if fenced is not None:
                if fence and fence.group(1)[0] == fenced:
                    fenced = None
                continue
            if fence:
                fenced = fence.group(1)[0]
                continue
            heading = _atx(line)
            if heading and heading[1]:
                level = len(heading[0])
                if level == 2:
                    self._close(section, links, items, strays)
                    section = heading[1].strip()
                    links = items = strays = 0
                    continue
                where = f"line {number + 1}"
                if level == 1:
                    self.warning("llms-second-h1", "a second H1", where)
                else:
                    self.warning(
                        "llms-heading",
                        f"an H{level} heading, where llmstxt.org has only the H1 "
                        "and H2 section headings",
                        where,
                    )
                continue
            if section is None or not line.strip():
                continue
            item = _ITEM.match(line)
            if item:
                items += 1
                if _LINK.match(item.group(1).strip()):
                    links += 1
            elif not line[:1].isspace():
                strays += 1
        self._close(section, links, items, strays)

    def _close(self, section: str | None, links: int, items: int, strays: int) -> None:
        if section is None:
            return
        self.sections.append(LlmsSection(section, links))
        if items > links:
            self.warning(
                "llms-not-a-link",
                f"{items - links} of the {items} list items in section {section!r} "
                "do not start with a markdown link [name](url)",
                section,
            )
        if strays:
            self.warning(
                "llms-not-a-list",
                f"section {section!r} holds {strays} line(s) of text outside its "
                "file list",
                section,
            )
        if not items and not strays:
            self.warning(
                "llms-empty-section",
                f"section {section!r} lists no files",
                section,
            )
