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
