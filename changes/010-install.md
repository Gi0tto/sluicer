### Changed

- A missing extra's message names the command that adds it for the way Sluicer was installed: `pip install`, `uv tool install` or `pipx install --force` with the extras already there, `uvx --from`, `uv add` in a uv project, or `uv pip install` in an environment uv made. It said `uv pip install "sluicer[x]"` to everyone, which uv refuses outside a virtual environment and which misses a `uv tool` or pipx one.
- `pip install sluicer` now turns a page into markdown: trafilatura is in the base install, so the one install line covers every command but the browser's. The `markdown` extra still installs, and brings nothing more; `mcp` no longer needs it. Measured on Python 3.14, the base install grows from 5 packages and 22 MB to 21 and 69 MB, and `import sluicer` takes as long as before.
- The Homebrew formula and the conda-forge recipe install trafilatura and its tree with the base package; the npm package still loads it only with its `markdown` option.

### Added

- `sluicer[all]` installs every extra but `stealth`, which stays asked for by name.
- `sluicer install browser` downloads the Chromium the `browser` extra drives, with Playwright's own installer and the Python Sluicer runs on, then checks that every part of it is there; without the extra, it prints the command that adds it and exits 2.
- `sluicer doctor` says what is installed, what each missing piece is for, and the command that adds it; it exits 2 when part of the base install is missing.
