import lxml.html
from hypothesis import given, strategies as st

from sluicer.structure.shape import alike, same_kind, telling


def element(html):
    return lxml.html.fromstring(html)


def test_two_items_of_the_same_kind_are_the_same_kind():
    one = element('<li class="row"><h3>A</h3><span class="price">1</span></li>')
    two = element('<li class="row"><h3>B</h3><span class="price">2</span></li>')

    assert same_kind(one, two)


def test_a_different_structure_is_a_different_kind_of_thing():
    item = element('<li class="row"><h3>A</h3></li>')
    other = element('<li class="row"><h3>A</h3><img src="x"></li>')

    assert not same_kind(item, other)


def test_one_optional_part_in_a_full_card_does_not_make_another_kind():
    """A badge one card has and its neighbours lack is a card, not a new shape."""
    card = (
        '<li class="row"><h3>A</h3><p><span>x</span></p><div><a>y</a>'
        "<img src='z'></div><span>{}</span></li>"
    )
    plain = element(card.format(""))
    badged = element(card.replace("<h3>A</h3>", "<h3>A</h3><em>new</em>"))

    assert same_kind(plain, badged)


def test_a_different_class_is_a_different_kind_of_thing():
    """The class attribute is most of what a page says about what a thing is."""
    row = element('<li class="row"><h3>A</h3></li>')
    banner = element('<li class="banner"><h3>A</h3></li>')

    assert not same_kind(row, banner)


def test_three_classes_are_compared_and_the_fourth_is_not():
    """Three is the bound: enough to tell two kinds apart, few enough to survive
    the utility classes that every framework sprays over the fourth onwards."""
    third_differs = element('<li class="a b c"><p>x</p></li>')
    third_agrees = element('<li class="a b d"><p>x</p></li>')

    assert not same_kind(third_differs, third_agrees)

    fourth_differs = element('<li class="a b c d"><p>x</p></li>')
    fourth_agrees = element('<li class="a b c e"><p>x</p></li>')

    assert same_kind(fourth_differs, fourth_agrees)


def test_a_class_below_the_member_does_not_split_the_kind():
    """books.toscrape.com writes each rating as a class on a descendant.

    ``p.star-rating.One`` and ``p.star-rating.Three`` are one card with two
    values, and comparing them as two shapes split twenty books into five
    groups, of which induction read the largest: six.
    """
    one = element(
        '<article class="product_pod"><p class="star-rating One"><i></i></p>'
        "<h3><a>A</a></h3></article>"
    )
    three = element(
        '<article class="product_pod"><p class="star-rating Three"><i></i></p>'
        "<h3><a>B</a></h3></article>"
    )

    assert same_kind(one, three)


def test_how_many_times_a_child_repeats_does_not_split_the_kind():
    """A quote with two tags and a quote with five are both quotes."""
    quote = '<div class="quote"><span>q</span><div>{}</div></div>'
    two = element(quote.format("<a>t</a>" * 2))
    five = element(quote.format("<a>t</a>" * 5))

    assert same_kind(two, five)


def test_the_default_depth_sees_past_the_first_generation():
    """A card and a card whose inner span holds a different element are not
    the same kind of thing, and the default has to be deep enough to say so."""
    bold = element("<div><p><span><b>x</b></span></p></div>")
    italic = element("<div><p><span><i>x</i></span></p></div>")

    assert not same_kind(bold, italic)


def test_the_default_depth_stops_at_three():
    """Two cards that differ only in how deeply their prose nests are two cards."""
    plain = element("<div><p><span><b>x</b></span></p></div>")
    nested = element("<div><p><span><b><em>x</em></b></span></p></div>")

    assert same_kind(plain, nested)


def test_the_words_inside_do_not_change_the_shape():
    short = element("<li><p>hi</p></li>")
    long = element("<li><p>" + ("a lot of words " * 50) + "</p></li>")

    assert same_kind(short, long)


def test_class_order_does_not_change_the_shape():
    one = element('<li class="a b"><p>x</p></li>')
    two = element('<li class="b a"><p>x</p></li>')

    assert same_kind(one, two)


def test_depth_is_bounded_so_a_deep_page_stays_comparable():
    shallow = element("<div><p>x</p></div>")
    deep = element("<div><p>x<em><b><i><u>deep</u></i></b></em></p></div>")

    assert same_kind(shallow, deep, depth=1)


_PATHS = st.frozensets(st.sampled_from([f"p{n}" for n in range(12)]), max_size=12)


@given(one=_PATHS, other=_PATHS, rarity=st.permutations(range(12)))
def test_two_alike_outlines_share_a_telling_path_whatever_the_order(one, other, rarity):
    """Siblings are compared only with groups that share a telling path, so
    two alike outlines that shared none would never be grouped."""

    def rank(path):
        return rarity[int(path[1:])], path

    if one and other and alike(one, other):
        assert set(telling(one, rank)) & set(telling(other, rank))


def test_alike_is_two_thirds_of_the_paths_both_hold():
    three = frozenset({"a", "b", "c"})

    assert alike(three, frozenset({"a", "b"}))
    assert not alike(three, frozenset({"a", "b", "d"}))
    assert alike(frozenset(), frozenset())
    assert not alike(frozenset(), frozenset({"a"}))
