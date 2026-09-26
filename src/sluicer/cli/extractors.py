"""``sluicer compile``, ``run`` and ``heal``: extractors learnt, replayed and healed.

An extractor is a JSON file; what it holds and how it is learnt is
``sluicer.extractor``'s. What is here is reading the pages it is given, what
each command says on stderr, and the exit codes: ``run`` and ``heal`` exit 3
when a page broke the contract or healing lost something.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from sluicer.cli.exits import CONTRACT_BROKEN, NOTHING_FOUND, _fail, _unreadable
from sluicer.cli.options import _with_proxy
from sluicer.cli.source import _read_pages
from sluicer.extractor import (
    LOSSES,
    Extractor,
    NothingToLearn,
    compile_extractor,
    heal as heal_extractor,
    run_extractor,
)
from sluicer.selectors import SelectorError


def _load_extractor(path: str) -> Extractor:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as failure:
        _fail(f"{_unreadable(path, failure)}.", failure)
    try:
        return Extractor.from_json(text)
    except ValueError as failure:
        _fail(f"{path} is not an extractor: {failure}", failure)


@click.command("compile")
@click.argument("sources", nargs=-1)
@click.option("-o", "--output", required=True, help="Where to write the extractor.")
@click.option(
    "--listing/--no-listing",
    default=None,
    help="Learn the rows the pages repeat (default: only if they declare no thing).",
)
@click.option(
    "--want",
    "wanted",
    multiple=True,
    metavar="NAME=VALUE",
    help="A value one row holds, and the column's name: --want price=41.90. "
    "Chooses the listing and keeps only the columns named.",
)
@click.option(
    "--select",
    "selected",
    multiple=True,
    metavar="NAME=SELECTOR",
    help="A field you name by CSS or XPath instead of an example: "
    "--select price='span.price::text'. No page is needed.",
)
@click.option(
    "--rows",
    metavar="SELECTOR",
    help="With --select, the rows of a listing, each field read inside each: "
    "--rows li.product.",
)
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
@_with_proxy
def compile_command(
    sources: tuple[str, ...],
    output: str,
    listing: bool | None,
    wanted: tuple[str, ...],
    selected: tuple[str, ...],
    rows: str | None,
    stealth: bool,
    no_robots: bool,
) -> None:
    """Learn an extractor from pages of one template, and write it to a file.

    With --want, the examples say which repeated group is the listing and
    what its columns are called: --want title="Brake pad set" --want
    price=41.90 learns the listing whose rows hold both, with those two
    columns. When no repeated group holds them -- a product page -- or with
    --no-listing, they are the page's own values, each learnt where it sits.
    A value that is nowhere is an error that names it.

    With --select, you name each field by selector instead, and --rows the
    listing's rows: nothing is learnt of where they are, and from the pages,
    if any are given, what each field looks like, as for any extractor. A
    selector that gives nothing on a page given is an error that names it.
    """
    if selected or rows is not None:
        _compile_selected(
            sources, output, listing, wanted, selected, rows, stealth, no_robots
        )
        return
    if not sources:
        _fail("compile needs pages to learn from, or fields named with --select.")
    want: dict[str, str] | None = None
    if wanted:
        want = {}
        for pair in wanted:
            name, equals, value = pair.partition("=")
            if not equals or not name.strip() or not value.strip():
                _fail(f"--want takes NAME=VALUE, not {pair!r}.")
            _named_once(name.strip(), want, "--want")
            want[name.strip()] = value
    pages = _read_pages(sources, stealth, no_robots)
    try:
        extractor = compile_extractor(
            pages, listing=listing, names=list(sources), want=want
        )
    except NothingToLearn as nothing:
        click.echo(f"Learnt nothing: {nothing}.", err=True)
        raise SystemExit(NOTHING_FOUND) from nothing
    _write(output, extractor.to_json())
    learnt = []
    if extractor.fields:
        learnt.append(
            f"{len(extractor.fields)} page fields ("
            + ", ".join(
                f"{f.name} after {f.anchor.label!r}"
                if f.anchor
                else f"{f.name} at {f.path}"
                for f in extractor.fields
            )
            + ")"
        )
    if extractor.listing is not None:
        counted = extractor.listing.rows
        learnt.append(
            f"a listing at {extractor.listing.container}, "
            f"{counted[0]}-{counted[1]} rows "
            f"of {len(extractor.listing.fields)} fields"
        )
    if extractor.summary:
        learnt.append(f"{len(extractor.summary)} summary answers")
    if extractor.types:
        learnt.append("declared " + ", ".join(extractor.types))
    click.echo(f"Learnt {'; '.join(learnt)}. Wrote {output}.", err=True)
    for note in extractor.notes:
        click.echo(f"Note: {note}.", err=True)


def _named_once(name: str, named: dict[str, str], option: str) -> None:
    """Refuse a field named twice, as a file with two is refused: the second
    was kept over the first, and the extractor had one field where two were
    asked for."""
    if name in named:
        _fail(f"two fields named {name!r}: each {option} names one field.")


def _compile_selected(
    sources: tuple[str, ...],
    output: str,
    listing: bool | None,
    wanted: tuple[str, ...],
    selected: tuple[str, ...],
    rows: str | None,
    stealth: bool,
    no_robots: bool,
) -> None:
    """``compile --select``: an extractor of fields a person named by selector.

    Every selector is read before any page is fetched, so one that cannot be
    read costs no request, and exits 2 naming it."""
    if not selected:
        _fail("--rows says where the rows of fields named with --select are.")
    if wanted:
        _fail("--select and --want name fields two ways; use one of them.")
    if listing is not None:
        _fail("With --select, --rows says where a listing's rows are, not --listing.")
    select: dict[str, str] = {}
    for pair in selected:
        name, equals, text = pair.partition("=")
        if not equals or not name.strip() or not text.strip():
            _fail(f"--select takes NAME=SELECTOR, not {pair!r}.")
        _named_once(name.strip(), select, "--select")
        select[name.strip()] = text
    try:
        compile_extractor([], select=select, rows=rows)
        extractor = compile_extractor(
            _read_pages(sources, stealth, no_robots),
            select=select,
            rows=rows,
            names=list(sources),
        )
    except SelectorError as unread:
        _fail(f"{unread}.", unread)
    except NothingToLearn as nothing:
        click.echo(f"Learnt nothing: {nothing}.", err=True)
        raise SystemExit(NOTHING_FOUND) from nothing
    _write(output, extractor.to_json())
    written = extractor.written
    assert written is not None
    where = f" in rows at {written.rows}" if written.rows is not None else ""
    learnt = [
        f"{len(written.fields)} fields by selector{where} ("
        + ", ".join(f"{f.name} at {f.selector}" for f in written.fields)
        + ")"
    ]
    if extractor.summary:
        learnt.append(f"{len(extractor.summary)} summary answers")
    if extractor.types:
        learnt.append("declared " + ", ".join(extractor.types))
    click.echo(f"Wrote {'; '.join(learnt)} to {output}.", err=True)
    for note in extractor.notes:
        click.echo(f"Note: {note}.", err=True)


def _write(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as failure:
        _fail(f"Could not write {path}: {failure.strerror or failure}", failure)


@click.command("run")
@click.argument("extractor_file")
@click.argument("sources", nargs=-1, required=True)
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
@_with_proxy
def run_command(
    extractor_file: str, sources: tuple[str, ...], stealth: bool, no_robots: bool
) -> None:
    """Replay an extractor on pages, and exit 3 if any page broke its contract."""
    extractor = _load_extractor(extractor_file)
    pages = []
    broken = False
    for source, (html, url) in zip(
        sources, _read_pages(sources, stealth, no_robots), strict=True
    ):
        run = run_extractor(extractor, html, url=url)
        failed = [asdict(check) for check in run.checks if not check.ok]
        pages.append(
            {
                "source": source,
                "url": run.url,
                "ok": run.ok,
                "rows": run.rows,
                "fields": run.fields,
                "summary": run.summary,
                "failed": failed,
            }
        )
        for check in run.checks:
            if not check.ok:
                broken = True
                click.echo(
                    f"FAILED {source}: expected {check.expected}, got {check.got}",
                    err=True,
                )
    click.echo(
        json.dumps(
            {"extractor": extractor_file, "pages": pages}, indent=2, ensure_ascii=False
        )
    )
    if broken:
        raise SystemExit(CONTRACT_BROKEN)


@click.command("heal")
@click.argument("extractor_file")
@click.argument("sources", nargs=-1, required=True)
@click.option("-o", "--output", help="Where to write the healed extractor.")
@click.option(
    "--force",
    is_flag=True,
    help="Write the healed extractor even when healing lost something; "
    "a lost listing is kept as it was.",
)
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
@_with_proxy
def heal_command(
    extractor_file: str,
    sources: tuple[str, ...],
    output: str | None,
    force: bool,
    stealth: bool,
    no_robots: bool,
) -> None:
    """Learn pages again and say what moved; write the result only with -o.

    Exits 3 when a field, a summary answer, a type or the listing was lost for
    good: healing moved what it could, and what it could not needs a person.
    Nothing is written then without --force, so a lossy extractor never
    quietly replaces the one that would have kept failing.
    """
    if force and not output:
        # Until 0.9.1 --force alone did nothing, and said nothing.
        raise click.UsageError(
            "--force writes the healed extractor even when healing lost "
            "something; it needs -o FILE to write it to."
        )
    extractor = _load_extractor(extractor_file)
    pages = _read_pages(sources, stealth, no_robots)
    try:
        healed, changes = heal_extractor(extractor, pages, names=list(sources))
    except NothingToLearn as nothing:
        click.echo(f"The pages hold nothing to heal from: {nothing}.", err=True)
        raise SystemExit(CONTRACT_BROKEN) from nothing
    for change in changes:
        if change.kind == "kept":
            continue
        if change.before and change.after:
            said = f"{change.kind}: {change.before} -> {change.after}"
            if change.evidence and change.evidence["samples"]:
                e = change.evidence
                said += (
                    f" ({e['seen']} of {e['samples']} learnt values found there;"
                    f" the next best place had {e['runner_up']})"
                )
            click.echo(said, err=True)
        else:
            click.echo(f"{change.kind}: {change.before or change.after}", err=True)
    listed = {f.name for f in extractor.listing.fields} if extractor.listing else set()
    gone = [c.before for c in changes if c.kind == "vanished" and c.before in listed]
    if gone and not any(c.kind in ("listing-lost", "container") for c in changes):
        # run says these fields broke and the listing held; heal says they
        # vanished. Both are so, and this says why the words differ.
        click.echo(
            f"The listing is where it was; {', '.join(map(str, gone))} "
            f"{'is' if len(gone) == 1 else 'are'} looked for by the values "
            "learnt, and no place in it holds them on these pages. Heal with a "
            "page that lists some of the same items to find where they went, "
            "or compile again.",
            err=True,
        )
    if any(c.kind == "broken" for c in changes):
        click.echo(
            "A selector you wrote no longer holds, and heal does not rewrite a "
            "selector a person wrote: find the new one with sluicer select on "
            "the new page, then compile again.",
            err=True,
        )
    lost = any(c.kind in LOSSES for c in changes)
    if output and (force or not lost):
        _write(output, healed.to_json())
        click.echo(f"Wrote {output}.", err=True)
    elif output:
        click.echo(
            f"Did not write {output}: healing lost data or left a move for you "
            "to decide. Pass --force to write it.",
            err=True,
        )
    click.echo(
        json.dumps(
            {"changes": [asdict(c) for c in changes]}, indent=2, ensure_ascii=False
        )
    )
    if lost:
        raise SystemExit(CONTRACT_BROKEN)
