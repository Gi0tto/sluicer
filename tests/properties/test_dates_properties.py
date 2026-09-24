"""A date is read in any language CLDR covers, and nothing else is made one.

Every month name in ``sluicer.calendar_names``, on any day of any year, in each
order the reader promises, must come back as that day; and no text at all may
make the reader raise or answer something that is not a date.
"""

from __future__ import annotations

import datetime
import re

from hypothesis import given, strategies as st

from sluicer.calendar_names import MONTHS
from sluicer.normalise import iso_date

_THAI = re.compile(f"[{chr(0x0E00)}-{chr(0x0E7F)}]")

days = st.dates(
    min_value=datetime.date(1000, 1, 1), max_value=datetime.date(9999, 12, 31)
)
names = st.sampled_from(sorted(MONTHS))
orders = st.sampled_from(
    [
        "{day} {name} {year}",
        "{day}. {name} {year}",
        "{day} de {name} de {year}",
        "{name} {day}, {year}",
        "{year} {name} {day}",
        "{year}. {name} {day}.",
    ]
)


@given(days, names, orders)
def test_every_month_name_on_every_day_is_that_day(day, name, order):
    """Where the name is that day's month, in an order the reader reads."""
    month = MONTHS[name]
    try:
        meant = day.replace(month=month)
    except ValueError:  # 31 in a month of 30
        meant = day.replace(month=month, day=28)
    written = order.format(day=meant.day, name=name, year=meant.year)
    year = meant.year
    if _THAI.search(name) and year >= 2400:
        year -= 543
    expected = f"{year:04d}-{meant.month:02d}-{meant.day:02d}"
    assert iso_date(written) == expected, written


@given(days)
def test_chinese_japanese_and_korean_numbers_with_units_are_that_day(day):
    for written in (
        f"{day.year}年{day.month}月{day.day}日",
        f"{day.year}년 {day.month}월 {day.day}일",
    ):
        assert iso_date(written) == day.isoformat(), written


@given(st.text(max_size=60))
def test_no_text_makes_the_reader_raise_or_answer_something_else(text):
    found = iso_date(text)
    if found is not None:
        datetime.date.fromisoformat(found[:10])
