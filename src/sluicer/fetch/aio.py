"""``fetch`` for a caller on an event loop, as polite as ``fetch`` on a thread.

The fetch layer is blocking by design -- ``http.client``, a browser on a
thread of its own, and a gate of threading locks that keeps one request at a
time to each site for the whole process (``sluicer.fetch.gate``). ``afetch``
runs ``fetch`` on a worker thread, so the loop keeps running while a page
comes, and the gate paces those threads exactly as it paces any other: a
coroutine's fetch, a thread's fetch and a crawl of one site all wait for
each other.

One thing is added on the loop's side. Without it, coroutines fetching one
site would each take a worker thread only to wait in the gate, and a loop's
few workers, all waiting for one slow site, would keep every other site
waiting behind it. So a coroutine first waits for its site on the loop, one
at a time for each site and loop, and takes a thread only when it is next;
the gate then decides when its request goes. Cancelling a coroutine still
waiting for its site asks nothing; one whose fetch has started can only stop
waiting for it, since a thread is not interrupted, and the fetch finishes, in
its turn, on its own.

``asyncio`` is imported when a coroutine is first made, not with the fetch
package: importing it costs more than a whole page's extraction.
"""

from __future__ import annotations

import functools
import threading
import weakref
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from sluicer.fetch.address import _resolve
from sluicer.fetch.gate import site_key
from sluicer.fetch.ladder import RungMemory, fetch
from sluicer.fetch.result import MAX_RESPONSE_BYTES, Fetched, Rung

if TYPE_CHECKING:
    import asyncio

_LOOPS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, weakref.WeakValueDictionary[str, asyncio.Lock]
] = weakref.WeakKeyDictionary()
"""For each running loop, a lock per site its coroutines are waiting for; a
site's is forgotten once nobody holds or waits for it."""

_LOOPS_LOCK = threading.Lock()
"""Guards ``_LOOPS``: two loops on two threads may each add their own."""


def _waiting_room(url: str) -> asyncio.Lock:
    """The lock ``url``'s site is waited for with on the running loop."""
    import asyncio

    loop = asyncio.get_running_loop()
    key = site_key(url)
    with _LOOPS_LOCK:
        sites = _LOOPS.get(loop)
        if sites is None:
            sites = _LOOPS[loop] = weakref.WeakValueDictionary()
        lock = sites.get(key)
        if lock is None:
            lock = sites[key] = asyncio.Lock()
        return lock


async def afetch(
    url: str,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    obey_robots: bool = True,
    stealth: bool = False,
    robots_reader: Callable[[str], str | None] | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    memory: RungMemory | None = None,
) -> Fetched:
    """``sluicer.fetch.fetch``, awaited: the same arguments, the same page,
    the same exceptions, and the event loop free while it is fetched.

    It runs on a worker thread of the loop's default executor. With the
    default rungs, coroutines fetching one site wait for it on the loop, one
    after another, and the process's gate then spaces their requests exactly
    as it spaces threads': robots.txt read once, one request to a site at a
    time, a second after anyone's last. Injected ``rungs`` are the caller's
    to pace, as for ``fetch``. Cancelled while it waits for its site, it asks
    nothing; cancelled once its fetch began, it stops waiting, and the fetch
    ends on its thread.
    """
    import asyncio

    call = functools.partial(
        fetch,
        url,
        rungs=rungs,
        obey_robots=obey_robots,
        stealth=stealth,
        robots_reader=robots_reader,
        allow_private=allow_private,
        resolve=resolve,
        max_bytes=max_bytes,
        proxy=proxy,
        headers=headers,
        cookies=cookies,
        memory=memory,
    )
    if rungs is not None:
        return await asyncio.to_thread(call)
    async with _waiting_room(url):
        return await asyncio.to_thread(call)
