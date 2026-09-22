---
name: Something read wrong
about: A page that Sluicer got wrong, or would not read at all
labels: bug
---

**The page.** A URL, or the HTML attached. Without it this is a guess.

**What Sluicer returned.** Paste the output of `sluicer extract <page>`.

**What the page actually declares.** The field, the value, and where in the
source it lives.

**Which is it:** a value that came back wrong, or a value that did not come back
at all? The second is a known cost we accept in places; the first is the kind of
bug this project takes seriously.

**Versions.** `sluicer --version`, your Python version, and whether the `fetch`
extra is installed.
