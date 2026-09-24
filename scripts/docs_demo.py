"""Publish the examples' made-up site with the documentation, under demo/.

MkDocs reads only docs/, and a link from there to examples/site would take the
pages out of the sdist: hatch walks a folder once, and the link is walked
first. This hook, named in mkdocs.yml, adds each file of examples/site to the
build instead, at the same path under demo/.
"""

from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files

SITE = Path(__file__).resolve().parent.parent / "examples" / "site"


def on_files(files: Files, config: MkDocsConfig) -> Files:
    for path in sorted(SITE.rglob("*")):
        if path.is_file():
            uri = f"demo/{path.relative_to(SITE).as_posix()}"
            files.append(File.generated(config, uri, abs_src_path=str(path)))
    return files
