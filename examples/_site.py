"""The small site in ``site/``, served on this machine so the examples need no web.

``serve()`` starts it on a free port and returns its address; it stops when the
example does. It holds an article that declares its author and date, a page of
notes that shows them but declares neither, and a robots.txt that asks every
crawler to stay out of ``drafts/``. The documentation site publishes the same
pages at https://gi0tto.github.io/sluicer/demo/.
"""

import functools
import http.server
import threading
from pathlib import Path

SITE = Path(__file__).with_name("site")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        """The examples print what matters; the server's log is not it."""


def serve() -> str:
    handler = functools.partial(_Quiet, directory=str(SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return f"http://{host}:{port}"
