from __future__ import annotations

from crawler.extractors.html import parse
from crawler.extractors.pii import is_personal_page, scrub


def test_scrub_removes_email_and_phone_but_keeps_part_data() -> None:
    s = scrub("Call +8801712345678 / 01712-345678, mail a.b@shop.com. 3.3V 2.4GHz 74HC595 1602 LCD 16x2")
    assert s is not None
    assert "@" not in s and "1712" not in s
    for keep in ("3.3V", "2.4GHz", "74HC595", "1602", "16x2"):
        assert keep in s


def test_profile_urls_and_person_pages_are_personal() -> None:
    empty = parse("<html><body></body></html>")
    assert is_personal_page(empty, "https://shop.test/members/rahim/")
    assert is_personal_page(empty, "https://shop.test/my-account/orders/")
    person = parse(
        '<script type="application/ld+json">{"@type":"ProfilePage","mainEntity":{"@type":"Person"}}</script>'
    )
    assert is_personal_page(person, "https://shop.test/x")


def test_product_with_review_author_is_not_personal() -> None:
    html = """<div itemscope itemtype="http://schema.org/Product"><span itemprop="name">X</span>
    <div itemprop="review" itemscope itemtype="http://schema.org/Review">
    <span itemprop="author" itemscope itemtype="http://schema.org/Person">A</span></div></div>"""
    assert not is_personal_page(parse(html), "https://shop.test/p/x")
