"""GTIN-8/12/13/14 validation (GS1 mod-10 check digit)."""

from __future__ import annotations


def normalize_gtin(raw: str | None) -> str | None:
    """Digits-only GTIN left-padded to 14, or None if invalid."""
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) not in (8, 12, 13, 14):
        return None
    if set(digits) == {"0"}:
        return None
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    if (10 - total % 10) % 10 != check:
        return None
    return digits.zfill(14)
