"""The child ``isolated`` starts imports only what its parent would.

Started as ``python -c``, the child put its working directory first on its
path, and imported ``pickle`` from there before it took the parent's path: a
``pickle.py`` in the folder an agent started ``sluicer mcp`` in -- a cloned
repository -- ran as soon as a selector tool was called. Found by review.
"""

from __future__ import annotations

from sluicer.isolated import isolated


def test_the_child_imports_nothing_from_its_working_directory(tmp_path, monkeypatch):
    marker = tmp_path / "ran"
    for name in ("pickle", "sys_stub", "sluicer"):
        (tmp_path / f"{name}.py").write_text(
            f"import pathlib\npathlib.Path({str(marker)!r}).write_text({name!r})\n",
            encoding="utf-8",
        )
    monkeypatch.chdir(tmp_path)

    assert isolated(len, "abc") == 3
    assert not marker.exists(), marker.read_text(encoding="utf-8")


def test_the_child_ignores_the_python_variables_of_its_environment(
    tmp_path, monkeypatch
):
    """PYTHONSTARTUP and PYTHONPATH are the environment's, not the parent's:
    the child imports from the path it is handed, and runs nothing else."""
    marker = tmp_path / "ran"
    (tmp_path / "startup.py").write_text(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('startup')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONSTARTUP", str(tmp_path / "startup.py"))
    (tmp_path / "pickle.py").write_text(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('path')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))

    assert isolated(len, "abcd") == 4
    assert not marker.exists(), marker.read_text(encoding="utf-8")


def test_a_call_s_selectors_stop_at_the_bound_even_when_its_budget_is_longer(
    monkeypatch,
):
    """A server's call budget is two minutes, and four hostile selectors held
    every reading worker for all of it: evaluation stops at ``SECONDS``."""
    import time

    import pytest

    from sluicer import isolated as module

    monkeypatch.setattr(module, "SECONDS", 0.5)
    started = time.monotonic()
    with module.until(time.monotonic() + 600), pytest.raises(module.TookTooLong):
        isolated(time.sleep, 30)
    assert time.monotonic() - started < 10
