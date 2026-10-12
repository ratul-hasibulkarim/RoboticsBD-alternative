"""LEGAL rule 6: never retain personal data.

* `is_personal_page` drops whole pages that are about a person (profiles, member pages).
* `scrub` removes e-mail addresses and phone numbers from any free text we keep
  (snippets, spec values) — a shop's support e-mail in a description is still removed.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from crawler.extractors import jsonld
from crawler.extractors.html import HTMLParser

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# International / BD mobile formats: +8801XXXXXXXXX, 01XXX-XXXXXX, (555) 555-5555, ...
_PHONE = re.compile(r"(?<![\w.])(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,5}(?![\w.])")
_PROFILE_PATH = re.compile(r"/(?:user|users|profile|profiles|member|members|account|my-account|customer|author)/", re.I)
_PERSON_TYPES = {"person", "profilepage"}


def is_personal_page(tree: HTMLParser, url: str) -> bool:
    if _PROFILE_PATH.search(urlsplit(url).path + "/"):
        return True
    types = jsonld.page_types(tree)
    if types & _PERSON_TYPES and "product" not in types:
        return True
    return (
        tree.css_first('[itemtype*="schema.org/Person"]') is not None
        and tree.css_first('[itemtype*="schema.org/Product"]') is None
    )


def scrub(text: str | None) -> str | None:
    if text is None:
        return None
    text = _EMAIL.sub("[email removed]", text)

    def _phone(m: re.Match[str]) -> str:
        digits = sum(c.isdigit() for c in m.group(0))
        return "[phone removed]" if digits >= 9 else m.group(0)

    return _PHONE.sub(_phone, text)
