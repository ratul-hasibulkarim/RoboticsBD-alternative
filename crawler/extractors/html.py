"""Small helpers over selectolax (lexbor backend)."""

from __future__ import annotations

from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

HTMLParser = LexborHTMLParser
Node = LexborNode


def parse(html: str | bytes) -> LexborHTMLParser:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    return LexborHTMLParser(html)


def text_of(node: LexborNode | None) -> str | None:
    if node is None:
        return None
    t = " ".join(node.text(separator=" ", strip=True).split())
    return t or None


def attr(node: LexborNode | None, name: str) -> str | None:
    if node is None:
        return None
    v = node.attributes.get(name)
    return v.strip() if v else None


def first_text(tree: LexborHTMLParser, *selectors: str) -> str | None:
    for sel in selectors:
        t = text_of(tree.css_first(sel))
        if t:
            return t
    return None


def absolutize(base: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("data:", "javascript:", "#")):
        return None
    return urljoin(base, href)


def table_specs(tree: LexborHTMLParser | LexborNode, selector: str) -> dict[str, str]:
    """Two-column spec table → dict. Works for <th>/<td> and <td>/<td> rows."""
    out: dict[str, str] = {}
    for table in tree.css(selector):
        for row in table.css("tr"):
            cells = row.css("th, td")
            if len(cells) >= 2:
                k, v = text_of(cells[0]), text_of(cells[1])
                if k and v:
                    out[k.rstrip(":")] = v
    return out
