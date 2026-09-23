from sluicer import extract
from sluicer.declared.rights import read_rights
from sluicer.document import load


def test_robots_directives_are_read_per_agent_in_order_each_once():
    page = (
        '<meta name="robots" content="NoIndex, nofollow">'
        '<meta name="robots" content="noai, noimageai, nofollow">'
        '<meta name="googlebot" content="nosnippet">'
        '<meta name="viewport" content="width=device-width">'
    )

    rights = read_rights(load(page))

    assert rights["robots"] == ["noindex", "nofollow", "noai", "noimageai"]
    assert rights["agents"] == {"googlebot": ["nosnippet"]}


def test_a_tdm_reservation_is_reported_as_the_page_wrote_it():
    page = (
        '<meta name="tdm-reservation" content="1">'
        '<meta name="tdm-policy" content="https://publisher.example/tdm-policy.json">'
    )

    rights = read_rights(load(page))

    assert rights == {
        "tdm_reservation": "1",
        "tdm_policy": "https://publisher.example/tdm-policy.json",
    }


def test_a_page_that_declares_nothing_is_reported_as_declaring_nothing():
    """Not as allowing everything: the two are different answers."""
    assert read_rights(load("<p>plain</p>")) == {}
    assert extract("<p>plain</p>").rights == {}


def test_a_hostile_page_cannot_make_the_answer_grow_with_it():
    many = ",".join(f"rule{n}" for n in range(1000))

    rights = read_rights(load(f'<meta name="robots" content="{many}">'))

    assert len(rights["robots"]) == 50
