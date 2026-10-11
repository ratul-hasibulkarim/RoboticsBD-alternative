"""Detect pages we must not use: login walls, CAPTCHA challenges, paywalls.

Detection is deliberately conservative (prefers false positives): a hit discards
the page and flags the source for human review. We never attempt to get past one.
"""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

_CAPTCHA_MARKERS = (
    "g-recaptcha",
    "h-captcha",
    "hcaptcha.com/1/api.js",
    "cf-challenge",
    "challenges.cloudflare.com",
    "cf_chl_opt",
    "/cdn-cgi/challenge-platform/",
    "px-captcha",
    "distil_r_captcha",
    "geetest_",
)
_CAPTCHA_TITLES = re.compile(
    r"(attention required|just a moment|are you a robot|verify you are human|access denied|captcha)",
    re.IGNORECASE,
)
_LOGIN_TITLES = re.compile(r"\b(log ?in|sign ?in|লগইন)\b", re.IGNORECASE)
_PAYWALL_JSONLD = re.compile(r'"isAccessibleForFree"\s*:\s*(false|"false"|"False")')


def detect_wall(html: str, *, status: int = 200) -> str | None:
    """Return 'captcha' | 'login' | 'paywall', or None if the page is usable."""
    lowered = html[:200_000].lower()
    if any(m in lowered for m in _CAPTCHA_MARKERS):
        return "captcha"

    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else ""
    if _CAPTCHA_TITLES.search(title) and status in (200, 403, 429, 503):
        return "captcha"

    if _PAYWALL_JSONLD.search(html):
        return "paywall"

    # A login wall: the page's main content is a password form and there is no product data.
    has_password = tree.css_first("input[type=password]") is not None
    if has_password:
        has_product = (
            '"@type":"product"' in lowered.replace(" ", "")
            or tree.css_first('[itemtype*="schema.org/Product"]') is not None
            or tree.css_first('meta[property="og:type"][content="product"]') is not None
        )
        if not has_product and (_LOGIN_TITLES.search(title) or len(tree.css("form")) <= 2):
            return "login"
    return None
