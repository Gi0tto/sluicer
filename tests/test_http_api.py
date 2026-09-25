"""The HTTP door: the MCP server's own tools, answered over HTTP.

In process, through starlette's TestClient, so no socket is opened; the tests
that need the real SDK and starlette skip without the ``api`` extra, and the
ones about its absence run everywhere. ``tests/live/api_check.py`` asks the
same questions of a real server over a real socket.

Nothing here fakes the MCP SDK. The door is only honest if an HTTP call goes
through the dispatch an MCP call does, so the real ``MCPServer`` is built every
time, and only the fetch below it is stood in for, by the fake the MCP tests
use, whose signature a test there pins to the real one.
"""

import asyncio
import json
import logging
import threading
from typing import get_args

import pytest
from click.testing import CliRunner

from sluicer import http_api
from sluicer.fetch import (
    AddressRefused,
    FetchFailed,
    PaymentRequired,
    RobotsRefused,
    SiteRefused,
)
from test_mcp_server import fake_fetch

PAGE = '<script type="application/ld+json">{"@type":"Product","name":"Pad"}</script>'
TOKEN = "a-token-for-the-tests"
AUTHORISED = {"Authorization": f"Bearer {TOKEN}"}


def _drift(name):
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "drift" / name).read_text(
        encoding="utf-8"
    )


@pytest.fixture
def client():
    """Make a TestClient over an app built from the real MCP server.

    Addressed to 127.0.0.1, as a local caller is: the app answers only requests
    addressed to this machine unless told otherwise, and TestClient's own
    default host is ``testserver``.
    """
    pytest.importorskip("starlette.testclient")
    pytest.importorskip("mcp.server.mcpserver")
    from starlette.testclient import TestClient

    def make(server=None, base_url="http://127.0.0.1:8000", **options):
        app = http_api.build_app(server, **options)
        return TestClient(app, base_url=base_url, raise_server_exceptions=False)

    return make


def _real_server():
    pytest.importorskip("mcp.server.mcpserver")
    from sluicer.mcp_server import build_server

    return build_server()


def test_every_tool_the_mcp_server_registers_is_listed_with_both_schemas(client):
    """Compared with the SDK's own listing, not with a list written here.

    A pinned list here would be the second copy this door exists not to have;
    the with-extras CI job pins the MCP server's list, and this holds the door
    to whatever that is.
    """
    server = _real_server()
    listed = client(server).get("/v1/tools").json()
    expected = [
        tool.model_dump(by_alias=True, exclude_none=True, mode="json")
        for tool in asyncio.run(server.list_tools())
    ]

    assert listed["ok"] is True
    assert listed["tools"] == expected
    for tool in listed["tools"]:
        assert tool["inputSchema"]["type"] == "object", tool["name"]
        assert tool["outputSchema"]["required"] == ["ok"], tool["name"]


def test_a_tool_the_server_gains_is_served_with_nothing_added_here(client):
    """What map_site, crawl_site and audit_page will rely on when they land."""
    from typing_extensions import TypedDict

    class Echo(TypedDict):
        ok: bool
        said: str

    server = _real_server()

    @server.tool()
    def echo(words: str) -> Echo:
        """Say it back."""
        return {"ok": True, "said": words}

    http = client(server)
    names = [tool["name"] for tool in http.get("/v1/tools").json()["tools"]]
    answer = http.post("/v1/tools/echo", json={"words": "hello"})

    assert "echo" in names
    assert answer.status_code == 200
    assert answer.json() == {"ok": True, "said": "hello"}


def test_an_http_call_answers_exactly_what_the_mcp_call_answers(client):
    server = _real_server()
    over_mcp = asyncio.run(server.call_tool("extract_declared", {"html_or_url": PAGE}))

    answer = client(server).post(
        "/v1/tools/extract_declared", json={"html_or_url": PAGE}
    )

    assert answer.status_code == 200
    assert answer.json() == over_mcp.structured_content
    assert answer.json()["summary"]["title"]["value"] == "Pad"


def test_the_status_table_names_every_code_a_tool_can_answer():
    """So a code a tool learns fails here, not as a 500 in a client."""
    pytest.importorskip("typing_extensions")
    from sluicer.mcp_answers import ErrorCode

    assert set(http_api.TOOL_STATUS) == set(get_args(ErrorCode))
    assert not set(http_api.TOOL_STATUS) & set(http_api.DOOR_STATUS)


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ({"ok": True, "records": []}, 200),
        ({"ok": False, "rows": [], "failed": [{"name": "field"}]}, 200),
        ({"ok": False, "lost": True, "changes": []}, 200),
        ({"ok": False, "error": {"code": "bad_input"}}, 400),
        ({"ok": False, "error": {"code": "refused_by_robots"}}, 403),
        ({"ok": False, "error": {"code": "refused_address"}}, 403),
        ({"ok": False, "error": {"code": "too_large"}}, 413),
        ({"ok": False, "error": {"code": "missing_extra"}}, 501),
        ({"ok": False, "error": {"code": "fetch_failed"}}, 502),
        ({"ok": False, "error": {"code": "timed_out"}}, 504),
        ({"ok": False, "error": {"code": "a code nobody wrote down"}}, 500),
    ],
)
def test_the_status_follows_the_answer(answer, status):
    assert http_api.status_of(answer) == status


def test_a_drifted_page_is_a_200_whose_answer_is_not_ok(client):
    """The request did what it asked: the tool read the page and found drift.

    A 4xx would tell an HTTP client that its request was wrong; it was right,
    and the finding is the answer. ``ok`` is what says not to use the rows.
    """
    http = client()
    learnt = http.post(
        "/v1/tools/compile_extractor",
        json={"pages": [_drift("shop_v1.html"), _drift("shop_v1_page2.html")]},
    ).json()
    drifted = http.post(
        "/v1/tools/run_extractor",
        json={
            "extractor": learnt["extractor"],
            "html_or_url": _drift("shop_prices_gone.html"),
        },
    )
    healed = http.post(
        "/v1/tools/heal_extractor",
        json={
            "extractor": learnt["extractor"],
            "pages": [_drift("shop_prices_gone.html")],
        },
    )

    assert drifted.status_code == 200
    assert drifted.json()["ok"] is False and drifted.json()["failed"]
    assert "error" not in drifted.json()
    assert healed.status_code == 200
    assert healed.json()["ok"] is False and healed.json()["lost"] is True


def test_a_page_that_keeps_to_its_extractor_replays_and_heals_over_http(client):
    http = client()
    learnt = http.post(
        "/v1/tools/compile_extractor", json={"pages": [_drift("shop_v1.html")]}
    ).json()
    healed = http.post(
        "/v1/tools/heal_extractor",
        json={
            "extractor": learnt["extractor"],
            "pages": [_drift("shop_redesigned.html")],
        },
    ).json()
    replayed = http.post(
        "/v1/tools/run_extractor",
        json={
            "extractor": healed["extractor"],
            "html_or_url": _drift("shop_redesigned.html"),
        },
    )

    assert replayed.status_code == 200
    assert replayed.json()["ok"] is True
    assert len(replayed.json()["rows"]) == 6


def test_each_tool_error_arrives_with_its_status(client, monkeypatch, absent):
    """One of every code the tools answer, each through the real dispatch."""
    url = "https://example.com/p"
    http = client()

    def fetched_with(raises):
        fake_fetch(monkeypatch, raises=raises)
        return http.post("/v1/tools/fetch_page", json={"url": url})

    answers = {
        "bad_input": http.post("/v1/tools/fetch_page", json={"url": PAGE}),
        "refused_by_robots": fetched_with(RobotsRefused(url)),
        "refused_by_site": fetched_with(SiteRefused(url, [], "a challenge page")),
        "payment_required": fetched_with(PaymentRequired(url, [])),
        "refused_address": fetched_with(AddressRefused(url, "it is private")),
        "fetch_failed": fetched_with(FetchFailed(url, [], "connection refused")),
    }
    monkeypatch.setattr("sluicer.mcp_server.MAX_RESPONSE_BYTES", 100)
    answers["too_large"] = http.post(
        "/v1/tools/extract_declared", json={"html_or_url": "<p>" + "x" * 200}
    )
    answers["tdm_reserved"] = http.post(
        "/v1/tools/extract_declared",
        json={
            "html_or_url": '<html><head><meta name="tdm-reservation" content="1">'
            "</head></html>",
            "respect_tdm": True,
        },
    )
    absent("trafilatura")
    answers["missing_extra"] = http.post(
        "/v1/tools/page_markdown", json={"html_or_url": PAGE}
    )

    assert set(answers) == set(http_api.TOOL_STATUS)
    for code, answer in answers.items():
        assert answer.status_code == http_api.TOOL_STATUS[code], code
        assert answer.json()["ok"] is False, code
        assert answer.json()["error"]["code"] == code
    assert answers["fetch_failed"].json()["error"]["retryable"] is True
    assert "sluicer[markdown]" in answers["missing_extra"].json()["error"]["message"]


def test_private_addresses_are_refused_unless_the_server_is_told(client, monkeypatch):
    """The tools read SLUICER_ALLOW_PRIVATE themselves, so the door changes nothing."""
    fetch = fake_fetch(monkeypatch)
    http = client()

    monkeypatch.delenv("SLUICER_ALLOW_PRIVATE", raising=False)
    http.post("/v1/tools/fetch_page", json={"url": "https://example.com/p"})
    monkeypatch.setenv("SLUICER_ALLOW_PRIVATE", "1")
    http.post("/v1/tools/fetch_page", json={"url": "https://example.com/p"})

    assert [call["allow_private"] for call in fetch.calls] == [False, True]


def test_a_token_is_asked_of_every_request_but_the_health_check(client):
    http = client(token=TOKEN)

    refused = http.get("/v1/tools")
    wrong = http.get("/v1/tools", headers={"Authorization": "Bearer not-it"})
    other_scheme = http.get("/v1/tools", headers={"Authorization": f"Basic {TOKEN}"})
    posted = http.post("/v1/tools/extract_declared", json={"html_or_url": PAGE})

    for answer in (refused, wrong, other_scheme, posted):
        assert answer.status_code == 401
        assert answer.json()["error"]["code"] == "unauthorized"
        assert answer.headers["www-authenticate"].startswith("Bearer")
    assert http.get("/health").json() == {"ok": True, "version": http_api.__version__}
    assert http.get("/v1/tools", headers=AUTHORISED).status_code == 200
    assert (
        http.get("/v1/tools", headers={"authorization": f"bearer {TOKEN}"}).status_code
        == 200
    )
    assert http.get("/openapi.json", headers=AUTHORISED).status_code == 200


def test_on_loopback_only_requests_addressed_to_this_machine_are_answered(client):
    """What stops a page in the user's browser reaching it by DNS rebinding."""
    local = client()
    exposed = client(local_only=False)

    rebound = local.get("/health", headers={"host": "attacker.example:8000"})

    assert rebound.status_code == 421
    assert rebound.json()["error"]["code"] == "misdirected"
    assert local.get("/health", headers={"host": "localhost:8000"}).status_code == 200
    assert local.get("/health", headers={"host": "[::1]:8000"}).status_code == 200
    assert (
        exposed.get("/health", headers={"host": "sluicer.example"}).status_code == 200
    )


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", False),
        ("::", False),
        ("10.0.0.1", False),
        ("sluicer.example", False),
        ("", False),
    ],
)
def test_loopback_is_this_machine_and_nothing_else(host, loopback):
    assert http_api.is_loopback(host) is loopback


@pytest.mark.parametrize(
    ("header", "local"),
    [
        ("127.0.0.1:8000", True),
        ("localhost", True),
        ("Localhost:1", True),
        ("[::1]:8000", True),
        ("[::1]", True),
        ("attacker.example", False),
        ("attacker.example:8000", False),
        ("attacker.example@127.0.0.1", False),
        ("127.0.0.1:http", False),
        ("[::1]x", False),
        ("", False),
        (None, False),
    ],
)
def test_the_host_a_request_names_is_read_as_a_browser_sends_it(header, local):
    assert http_api._addressed_locally(header) is local


def test_what_the_door_refuses_before_any_tool_runs(client, monkeypatch):
    """Each of these must reach no tool: a text/plain POST is one a web page
    can send cross-origin without asking first, so it is refused unread."""
    fetch = fake_fetch(monkeypatch)
    http = client()
    tool = "/v1/tools/fetch_page"
    arguments = json.dumps({"url": "https://example.com/p"})
    nested = "[" * 100_000 + "]" * 100_000

    answers = {
        "unknown tool": (http.post("/v1/tools/nope", json={}), 404, "not_found"),
        "text/plain": (
            http.post(tool, content=arguments, headers={"content-type": "text/plain"}),
            415,
            "unsupported_media_type",
        ),
        "no content type": (http.post(tool, content=arguments), 415, None),
        "not json": (
            http.post(tool, content="{", headers={"content-type": "application/json"}),
            400,
            "bad_input",
        ),
        "not an object": (http.post(tool, json=["https://example.com/p"]), 400, None),
        "nested too deep": (
            http.post(
                tool, content=nested, headers={"content-type": "application/json"}
            ),
            400,
            "bad_input",
        ),
        "wrong arguments": (http.post(tool, json={"link": "x"}), 400, "bad_input"),
        "wrong method": (http.get(tool), 405, "method_not_allowed"),
        "unknown path": (http.get("/v2/nothing"), 404, "not_found"),
    }

    for case, (answer, status, code) in answers.items():
        assert answer.status_code == status, case
        assert answer.json()["ok"] is False, case
        if code is not None:
            assert answer.json()["error"]["code"] == code, case
    assert fetch.calls == []
    assert answers["wrong method"][0].headers["allow"] == "POST"


def test_arguments_that_do_not_fit_are_named_field_by_field(client):
    answer = (
        client().post("/v1/tools/extract_declared", json={"induce": "sometimes"}).json()
    )

    assert answer["error"]["message"] == (
        "the arguments do not fit extract_declared's input schema: "
        "html_or_url: Field required; "
        "induce: Input should be a valid boolean, unable to interpret input"
    )


def test_a_body_over_the_bound_is_refused_declared_or_not(client, monkeypatch):
    fetch = fake_fetch(monkeypatch)
    http = client(max_body=100)
    heavy = json.dumps({"url": "https://example.com/" + "p" * 200}).encode()

    def chunks():
        yield heavy[:60]
        yield heavy[60:]

    declared = http.post(
        "/v1/tools/fetch_page",
        content=heavy,
        headers={"content-type": "application/json"},
    )
    streamed = http.post(
        "/v1/tools/fetch_page",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    within = http.post("/v1/tools/fetch_page", json={"url": "https://example.com/p"})

    for answer in (declared, streamed):
        assert answer.status_code == 413
        assert answer.json()["error"]["code"] == "too_large"
    assert within.status_code == 200
    assert [call["url"] for call in fetch.calls] == ["https://example.com/p"]


def test_a_call_over_its_budget_is_answered_and_a_queued_one_never_starts(
    client, monkeypatch
):
    """The call that ran out still ends on its worker; the one waiting behind it
    is never started, and the next call runs as soon as the worker is free."""
    fetch = fake_fetch(monkeypatch, html=PAGE)
    released = threading.Event()

    def slow(url, **options):
        if url.endswith("/slow"):
            released.wait(10)
        return fetch(url, **options)

    monkeypatch.setattr("sluicer.fetch.fetch", slow)
    http = client(timeout=0.3, max_calls=1)
    try:
        ran_out = http.post(
            "/v1/tools/fetch_page", json={"url": "https://a.example/slow"}
        )
        queued = http.post("/v1/tools/fetch_page", json={"url": "https://b.example/q"})
    finally:
        released.set()
    after = http.post("/v1/tools/fetch_page", json={"url": "https://c.example/next"})

    for answer in (ran_out, queued):
        assert answer.status_code == 504
        assert answer.json()["error"] | {"message": ""} == {
            "code": "timed_out",
            "message": "",
            "retryable": True,
        }
    assert after.status_code == 200
    assert [call["url"] for call in fetch.calls] == [
        "https://a.example/slow",
        "https://c.example/next",
    ]


def test_a_hostile_selector_cannot_hold_a_worker_past_its_budget(client):
    """A selector that would run for minutes once held its worker for as long
    as it ran: four of them froze a server. Evaluated in a process of its
    own, it is stopped when its call's budget ends, and the one worker it
    held answers the next call."""
    import time

    from test_mcp_server import HOSTILE_PAGE, HOSTILE_SELECTOR

    http = client(timeout=2, max_reads=1)
    with http:
        began = time.monotonic()
        hostile = http.post(
            "/v1/tools/select_values",
            json={"html_or_url": HOSTILE_PAGE, "selector": HOSTILE_SELECTOR},
        )
        after = http.post(
            "/v1/tools/select_values",
            json={"html_or_url": "<p>x</p>", "selector": "//p"},
        )
        took = time.monotonic() - began

    assert hostile.status_code in (400, 504)
    assert after.status_code == 200
    assert after.json()["count"] == 1
    assert took < 8


def _holding_every_fetch_worker(monkeypatch, calls, many=http_api.MAX_CALLS):
    """Start ``many`` fetches that hang until released, once each has started.

    ``calls(url)`` sends one call that fetches ``url``; each goes to a site of
    its own, so no site's turn is what holds them. Returns the event that
    releases them and the threads sending them.
    """
    fetch = fake_fetch(monkeypatch, html=PAGE)
    released = threading.Event()
    started = threading.Semaphore(0)

    def slow(url, **options):
        started.release()
        released.wait(10)
        return fetch(url, **options)

    monkeypatch.setattr("sluicer.fetch.fetch", slow)
    senders = [
        threading.Thread(target=calls, args=(f"https://s{n}.example/slow",))
        for n in range(many)
    ]
    for sender in senders:
        sender.start()
    for _ in senders:
        assert started.acquire(timeout=10), "a slow fetch never started"
    return released, senders


def test_a_call_that_fetches_nothing_never_waits_behind_calls_that_fetch(
    client, monkeypatch
):
    """Four slow sites held every worker, and extract_declared on HTML handed
    in, which reaches no network, waited behind them: 504 at its budget here,
    about 65 s of HTTP, browser and robots.txt deadlines in a real server."""
    import time

    http = client(timeout=3)
    with http:
        released, senders = _holding_every_fetch_worker(
            monkeypatch,
            lambda url: http.post("/v1/tools/fetch_page", json={"url": url}),
        )
        try:
            began = time.monotonic()
            answer = http.post("/v1/tools/extract_declared", json={"html_or_url": PAGE})
            took = time.monotonic() - began
        finally:
            released.set()
            for sender in senders:
                sender.join(10)

    assert answer.status_code == 200
    assert answer.json()["summary"]["title"]["value"] == "Pad"
    assert took < 0.5


@pytest.mark.parametrize(
    ("arguments", "fetches"),
    [
        ({"html_or_url": PAGE}, False),
        ({"html_or_url": "https://example.com/p"}, True),
        ({"html_or_url": "  HTTP://example.com/p"}, True),
        ({"url": "https://example.com/p", "limit": 5}, True),
        ({"url": PAGE}, False),
        ({"url_or_text": "<rss/>"}, False),
        ({"pages": [PAGE, PAGE]}, False),
        ({"pages": [PAGE, "https://example.com/p"]}, True),
        (
            {"extractor": {"learnt_from": ["https://example.com/p"]}, "pages": [PAGE]},
            False,
        ),
        ({"html_or_url": 12}, True),
        ({"words": "hello"}, True),
        ({}, True),
    ],
)
def test_a_call_may_fetch_unless_every_page_it_names_is_handed_in(arguments, fetches):
    """Read as the tools read a page: an http(s) URL is fetched, anything else
    is the page. A call that names no page is taken to fetch, the safe side."""
    assert http_api.may_fetch(arguments) is fetches


def test_every_tool_names_its_page_where_the_door_looks_for_it():
    """A tool whose page came in under another name would be taken to fetch,
    and wait behind the calls that do, even with its page handed in."""
    server = _real_server()
    for tool in asyncio.run(server.list_tools()):
        named = set(tool.input_schema["properties"]) & set(http_api.PAGE_ARGUMENTS)
        assert named, tool.name


def test_a_real_bug_in_a_tool_is_a_500_that_keeps_its_traceback_in_the_log(
    client, monkeypatch, caplog
):
    def broken(*args, **kwargs):
        raise ValueError("a bug")

    monkeypatch.setattr("sluicer.mcp_server.extract", broken)

    with caplog.at_level(logging.ERROR, logger="sluicer.http_api"):
        answer = client().post("/v1/tools/extract_declared", json={"html_or_url": PAGE})

    assert answer.status_code == 500
    assert answer.json()["error"]["code"] == "internal_error"
    assert "a bug" not in answer.text
    logged = [record for record in caplog.records if record.name == "sluicer.http_api"]
    assert logged and logged[0].exc_info is not None


def test_a_tool_that_refuses_on_purpose_is_a_bad_input(client):
    from mcp.server.mcpserver.exceptions import ToolError

    server = _real_server()

    @server.tool()
    def picky(word: str) -> dict:
        """Refuse everything."""
        raise ToolError(f"not {word}")

    answer = client(server).post("/v1/tools/picky", json={"word": "that"})

    assert answer.status_code == 400
    assert answer.json()["error"]["message"] == ("Error executing tool picky: not that")


def test_every_tool_of_ours_answers_with_structured_content(client):
    """A tool with no output schema has no answer to send; ours all have one."""
    server = _real_server()
    for tool in asyncio.run(server.list_tools()):
        assert tool.output_schema is not None, tool.name

    @server.tool(structured_output=False)
    def shapeless() -> str:
        """Answer in text only."""
        return "words"

    answer = client(server).post("/v1/tools/shapeless", json={})

    assert answer.status_code == 500
    assert "output schema" in answer.json()["error"]["message"]


def test_a_failure_in_the_door_itself_is_still_an_answer(client, monkeypatch):
    server = _real_server()

    async def broken():
        raise RuntimeError("the door broke")

    monkeypatch.setattr(server, "list_tools", broken)
    answer = client(server).get("/v1/tools")

    assert answer.status_code == 500
    assert answer.json() == http_api.refusal(
        "internal_error", "the server failed; its log has the traceback"
    )


def test_the_app_starts_and_stops_its_workers(client):
    http = client()
    with http:
        assert http.get("/health").status_code == 200


def _resolved(node, document):
    """Inline every local $ref, so two schemas can be compared by what they say."""
    if isinstance(node, dict):
        if "$ref" in node:
            target = document
            for part in node["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            return _resolved(target, document)
        return {
            key: _resolved(value, document)
            for key, value in node.items()
            if key != "$defs"
        }
    if isinstance(node, list):
        return [_resolved(item, document) for item in node]
    return node


def test_the_openapi_document_says_what_each_tool_takes_and_answers(client):
    """Every reference resolves, and each tool's request and answer schemas say
    exactly what its MCP schemas say once the references are followed."""
    http = client(token=TOKEN)
    document = http.get("/openapi.json", headers=AUTHORISED).json()
    tools = http.get("/v1/tools", headers=AUTHORISED).json()["tools"]

    assert document["openapi"] == "3.1.0"
    assert document["info"]["version"] == http_api.__version__
    assert document["security"] == [{"bearer": []}]
    assert document["paths"]["/health"]["get"]["security"] == []
    for tool in tools:
        post = document["paths"][f"/v1/tools/{tool['name']}"]["post"]
        body = post["requestBody"]["content"]["application/json"]["schema"]
        answer = post["responses"]["200"]["content"]["application/json"]["schema"]
        assert post["operationId"] == tool["name"]
        assert _resolved(body, document) == _resolved(
            tool["inputSchema"], tool["inputSchema"]
        )
        assert _resolved(answer, document) == _resolved(
            tool["outputSchema"], tool["outputSchema"]
        )
        assert {
            "400",
            "401",
            "402",
            "403",
            "413",
            "415",
            "421",
            "451",
            "500",
            "501",
            "502",
            "504",
        } == (set(post["responses"]) - {"200"})
    assert "$defs" not in json.dumps(document)


def test_the_openapi_document_leaves_out_what_this_server_cannot_answer():
    document = http_api.openapi_document([], secured=False, local_only=False)
    listing = document["paths"]["/v1/tools"]["get"]["responses"]

    assert "security" not in document
    assert "securitySchemes" not in document["components"]
    assert "401" not in listing and "421" not in listing
    assert "404" not in listing


def test_two_tools_whose_definitions_share_a_name_keep_their_own():
    """Filed under the tool's name when they differ, shared when they agree."""

    def tool(name, kind):
        return {
            "name": name,
            "description": f"{name}.\n\nMore.",
            "inputSchema": {"type": "object"},
            "outputSchema": {
                "type": "object",
                "properties": {"page": {"$ref": "#/$defs/Page"}},
                "$defs": {"Page": {"type": kind}},
            },
        }

    document = http_api.openapi_document(
        [tool("one", "string"), tool("two", "integer"), tool("three", "string")],
        secured=False,
        local_only=True,
    )
    schemas = document["components"]["schemas"]

    def page_of(name):
        post = document["paths"][f"/v1/tools/{name}"]["post"]
        answer = post["responses"]["200"]["content"]["application/json"]["schema"]
        return _resolved(answer, document)["properties"]["page"]

    assert page_of("one") == {"type": "string"}
    assert page_of("two") == {"type": "integer"}
    assert page_of("three") == {"type": "string"}
    assert set(schemas) >= {"Page", "two.Page"} and "three.Page" not in schemas
    assert document["paths"]["/v1/tools/one"]["post"]["summary"] == "one."


def test_without_the_extra_building_the_app_says_how_to_install_it(absent):
    absent("starlette")

    with pytest.raises(http_api.ApiExtraMissing) as raised:
        http_api.build_app()

    assert 'uv pip install "sluicer[api]"' in str(raised.value)
    assert raised.value.extra == "api"


def test_without_the_sdk_building_the_app_names_it(absent):
    pytest.importorskip("starlette")
    absent("mcp")

    with pytest.raises(http_api.ApiExtraMissing) as raised:
        http_api.build_app()

    assert "the mcp package" in str(raised.value)
    assert "sluicer[api]" in str(raised.value)


@pytest.fixture
def uvicorn_run(monkeypatch):
    """Stand in for ``uvicorn.run``, recording what it was handed."""
    import sys
    import types

    ran = {}
    module = types.ModuleType("uvicorn")
    module.run = lambda app, **options: ran.update(app=app, **options)
    monkeypatch.setitem(sys.modules, "uvicorn", module)
    return ran


def test_serve_refuses_to_listen_beyond_loopback_without_a_token(
    monkeypatch, uvicorn_run
):
    monkeypatch.delenv(http_api.TOKEN_ENV, raising=False)

    with pytest.raises(http_api.Unprotected) as raised:
        http_api.serve("0.0.0.0", 8000)

    assert http_api.TOKEN_ENV in str(raised.value)
    assert "--allow-unauthenticated" in str(raised.value)
    assert uvicorn_run == {}


@pytest.mark.parametrize(
    ("host", "token", "forced", "local_only"),
    [
        ("127.0.0.1", None, False, True),
        ("localhost", TOKEN, False, True),
        ("0.0.0.0", TOKEN, False, False),
        ("0.0.0.0", None, True, False),
    ],
)
def test_serve_listens_where_it_is_safe_or_told_to(
    client, monkeypatch, uvicorn_run, host, token, forced, local_only
):
    from starlette.testclient import TestClient

    if token:
        monkeypatch.setenv(http_api.TOKEN_ENV, token)
    else:
        monkeypatch.delenv(http_api.TOKEN_ENV, raising=False)

    http_api.serve(host, 8123, timeout=5, allow_unauthenticated=forced)

    assert uvicorn_run["host"] == host and uvicorn_run["port"] == 8123
    assert uvicorn_run["limit_concurrency"] == http_api.MAX_CONNECTIONS
    http = TestClient(uvicorn_run["app"], base_url="http://sluicer.example")
    health = http.get("/health")
    listing = http.get("/v1/tools", headers=AUTHORISED if token else {})
    assert health.status_code == (421 if local_only else 200)
    if not local_only:
        assert listing.status_code == 200
        assert http.get("/v1/tools").status_code == (401 if token else 200)


def test_serve_without_uvicorn_says_how_to_install_it(monkeypatch, absent):
    monkeypatch.delenv(http_api.TOKEN_ENV, raising=False)
    absent("uvicorn")

    with pytest.raises(http_api.ApiExtraMissing) as raised:
        http_api.serve()

    assert "sluicer[api]" in str(raised.value)


def test_the_command_hands_its_options_to_the_server(monkeypatch):
    from sluicer import cli

    seen = {}
    monkeypatch.setattr(
        "sluicer.cli.servers.serve_http",
        lambda host, port, **options: seen.update(host=host, port=port, **options),
    )
    monkeypatch.setenv(http_api.TOKEN_ENV, TOKEN)

    result = CliRunner().invoke(
        cli.main, ["serve", "--host", "0.0.0.0", "--port", "9000", "--timeout", "30"]
    )

    assert result.exit_code == 0, result.output
    assert seen == {
        "host": "0.0.0.0",
        "port": 9000,
        "timeout": 30.0,
        "allow_unauthenticated": False,
    }


@pytest.mark.parametrize(
    ("host", "token", "said"),
    [
        ("127.0.0.1", None, "no token, answering only requests addressed to this"),
        ("0.0.0.0", TOKEN, "with a token."),
    ],
)
def test_serve_says_what_protects_it_once_it_is_sure_to_listen(
    client, monkeypatch, uvicorn_run, capsys, host, token, said
):
    if token:
        monkeypatch.setenv(http_api.TOKEN_ENV, token)
    else:
        monkeypatch.delenv(http_api.TOKEN_ENV, raising=False)

    http_api.serve(host)

    assert said in capsys.readouterr().err


def test_the_command_exits_2_rather_than_serve_unprotected(monkeypatch, uvicorn_run):
    from sluicer import cli

    monkeypatch.delenv(http_api.TOKEN_ENV, raising=False)

    result = CliRunner().invoke(cli.main, ["serve", "--host", "0.0.0.0"])

    assert result.exit_code == 2
    assert uvicorn_run == {}
    assert "serving" not in result.stderr
    assert "Refusing to listen on 0.0.0.0 with no token" in result.stderr
    assert "Traceback" not in result.output


def test_the_command_without_the_extra_is_a_message_not_a_traceback(
    monkeypatch, absent
):
    from sluicer import cli

    monkeypatch.delenv(http_api.TOKEN_ENV, raising=False)
    absent("uvicorn")

    result = CliRunner().invoke(cli.main, ["serve"])

    assert result.exit_code == 2
    assert 'uv pip install "sluicer[api]"' in result.stderr
