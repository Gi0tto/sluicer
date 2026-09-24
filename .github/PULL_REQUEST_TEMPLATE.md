**What changes, in one sentence.**

**The test that proves it.** Name it. It should fail without your change; say
that you watched it fail, and for which reason.

**Measured, not assumed.** If you claim it is faster, more accurate or reads
more pages, say by how much and against what.

**Checklist**

- [ ] `uv run --extra api pytest -q --cov`, `uv run ruff check src tests` and `uv run mypy` pass
- [ ] A line in `CHANGELOG.md` under `Unreleased`, if a user would notice the change
- [ ] No network access in any test
- [ ] No LLM call and no paid API anywhere in the path
- [ ] Annotations are honest: nothing typed `object` that has a known type
- [ ] English in code, comments, tests and commit messages
- [ ] AI assistance, if any, said and roughly how much, as `AI_POLICY.md` asks
