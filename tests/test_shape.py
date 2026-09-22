import lxml.html

from sluicer.induce.shape import signature


def element(html):
    return lxml.html.fromstring(html)


def test_two_items_of_the_same_kind_share_a_signature():
    one = element('<li class="row"><h3>A</h3><span class="price">1</span></li>')
    two = element('<li class="row"><h3>B</h3><span class="price">2</span></li>')

    assert signature(one) == signature(two)


def test_different_shapes_do_not_share_a_signature():
    item = element('<li class="row"><h3>A</h3></li>')
    other = element('<li class="row"><h3>A</h3><img src="x"></li>')

    assert signature(item) != signature(other)


def test_a_different_class_is_a_different_kind_of_thing():
    """The class attribute is most of what a page says about what a thing is."""
    row = element('<li class="row"><h3>A</h3></li>')
    banner = element('<li class="banner"><h3>A</h3></li>')

    assert signature(row) != signature(banner)


def test_three_classes_are_compared_and_the_fourth_is_not():
    """Three is the bound: enough to tell two kinds apart, few enough to survive
    the utility classes that every framework sprays over the fourth onwards."""
    third_differs = element('<li class="a b c"><p>x</p></li>')
    third_agrees = element('<li class="a b d"><p>x</p></li>')

    assert signature(third_differs) != signature(third_agrees)

    fourth_differs = element('<li class="a b c d"><p>x</p></li>')
    fourth_agrees = element('<li class="a b c e"><p>x</p></li>')

    assert signature(fourth_differs) == signature(fourth_agrees)


def test_the_default_depth_sees_past_the_first_generation():
    """A card and a card whose inner span holds a different element are not
    the same kind of thing, and the default has to be deep enough to say so."""
    bold = element("<div><p><span><b>x</b></span></p></div>")
    italic = element("<div><p><span><i>x</i></span></p></div>")

    assert signature(bold) != signature(italic)


def test_the_default_depth_stops_at_three():
    """Two cards that differ only in how deeply their prose nests are two cards."""
    plain = element("<div><p><span><b>x</b></span></p></div>")
    nested = element("<div><p><span><b><em>x</em></b></span></p></div>")

    assert signature(plain) == signature(nested)


def test_the_words_inside_do_not_change_the_shape():
    short = element("<li><p>hi</p></li>")
    long = element("<li><p>" + ("a lot of words " * 50) + "</p></li>")

    assert signature(short) == signature(long)


def test_class_order_does_not_change_the_shape():
    one = element('<li class="a b"><p>x</p></li>')
    two = element('<li class="b a"><p>x</p></li>')

    assert signature(one) == signature(two)


def test_depth_is_bounded_so_a_deep_page_stays_comparable():
    shallow = element("<div><p>x</p></div>")
    deep = element("<div><p>x<em><b><i><u>deep</u></i></b></em></p></div>")

    assert signature(shallow, depth=1) == signature(deep, depth=1)
