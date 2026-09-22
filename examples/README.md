# Examples

Each file runs on its own and needs the extras:

```bash
uv tool install 'sluicer[fetch,markdown]'
python 01_declared_fields.py
```

`01` shows the declared data with the provenance of every field, and what the
fetch cost. `02` shows a site refusing us and being obeyed. `03` turns a page
into readable markdown.
