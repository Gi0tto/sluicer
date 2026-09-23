"""The schedule on its own: one request at a time per site, rested, in order."""

from itertools import pairwise

import pytest

from fake_site import Clock
from sluicer.crawl.schedule import Politeness, Queue, Schedule

ROOT = "https://example.com"


def test_a_schedule_needs_room_for_one_request():
    with pytest.raises(ValueError):
        Schedule(lambda task: task, Politeness(lambda url: None), concurrency=0)


def test_a_bug_in_a_visit_is_raised_not_turned_into_a_page():
    clock = Clock()
    queue = Queue()
    queue.add(f"{ROOT}/")

    def visit(task):
        raise KeyError("a bug")

    for concurrency in (1, 2):
        polite = Politeness(lambda url: None, clock=clock, sleep=clock.sleep)
        schedule = Schedule(visit, polite, concurrency=concurrency)
        with pytest.raises(KeyError):
            list(schedule.run(queue, lambda task, result: None))
        queue.add(f"{ROOT}/")


def test_a_schedule_waits_for_the_next_site_to_rest_when_nothing_else_can_run():
    clock = Clock()
    polite = Politeness(lambda url: None, min_delay=5.0, clock=clock, sleep=clock.sleep)
    queue = Queue()
    for n in range(3):
        queue.add(f"{ROOT}/{n}")
    started = []

    def visit(task):
        started.append(clock())
        polite.ended(task.url)
        return task.url

    list(Schedule(visit, polite, concurrency=1).run(queue, lambda t, r: None))

    assert [round(b - a, 6) for a, b in pairwise(started)] == [5.0, 5.0]


def test_a_queue_serves_no_further_than_it_is_told():
    queue = Queue()
    for n in range(3):
        queue.add(f"https://site{n}.example/")

    assert queue.take(lambda site: site != "site0.example", below=1) is None
    assert queue.take(lambda site: site != "site0.example", below=3).seq == 1


def test_a_full_schedule_waits_for_a_request_to_end_rather_than_spinning(
    monkeypatch,
):
    """With every worker busy and another site due, a timeout would only spin."""
    import time
    from concurrent.futures import wait as real_wait

    waits = []

    def counting(futures, timeout=None, return_when=None):
        waits.append(timeout)
        return real_wait(futures, timeout=timeout, return_when=return_when)

    monkeypatch.setattr("sluicer.crawl.schedule.wait", counting)
    polite = Politeness(lambda url: None, min_delay=0.0)
    queue = Queue()
    for n in range(6):
        queue.add(f"https://site{n % 3}.example/{n}")

    def visit(task):
        time.sleep(0.05)
        polite.ended(task.url)
        return task.url

    done = list(Schedule(visit, polite, concurrency=2).run(queue, lambda t, r: None))

    assert len(done) == 6
    assert len(waits) < 20, f"{len(waits)} waits for six requests"
