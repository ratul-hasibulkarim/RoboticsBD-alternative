"""Price string parsing and minor-unit conversion."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ISO 4217 minor-unit exponents for currencies we can encounter. Default 2.
MINOR_EXPONENT: dict[str, int] = {
    "BDT": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CNY": 2,
    "INR": 2,
    "PKR": 2,
    "LKR": 2,
    "NPR": 2,
    "SGD": 2,
    "MYR": 2,
    "THB": 2,
    "AUD": 2,
    "CAD": 2,
    "HKD": 2,
    "AED": 2,
    "SAR": 2,
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "KWD": 3,
    "BHD": 3,
    "OMR": 3,
}

# Order matters: longer / more specific tokens first.
_SYMBOLS: list[tuple[str, str]] = [
    ("US$", "USD"),
    ("USD", "USD"),
    ("BDT", "BDT"),
    ("TK.", "BDT"),
    ("TK", "BDT"),
    ("TAKA", "BDT"),
    ("টাকা", "BDT"),
    ("৳", "BDT"),
    ("EUR", "EUR"),
    ("€", "EUR"),
    ("GBP", "GBP"),
    ("£", "GBP"),
    ("RMB", "CNY"),
    ("CNY", "CNY"),
    ("CN¥", "CNY"),
    ("JPY", "JPY"),
    ("INR", "INR"),
    ("₹", "INR"),
    ("RS.", "INR"),
    ("S$", "SGD"),
    ("SGD", "SGD"),
    ("A$", "AUD"),
    ("AUD", "AUD"),
    ("C$", "CAD"),
    ("CAD", "CAD"),
    ("HK$", "HKD"),
    ("$", "USD"),
    ("¥", "CNY"),
]

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_NUMBER = re.compile(r"\d[\d.,\s  ']*")


def minor_exponent(currency: str) -> int:
    return MINOR_EXPONENT.get(currency.upper(), 2)


def to_minor(amount: Decimal, currency: str) -> int:
    exp = minor_exponent(currency)
    return int((amount * (Decimal(10) ** exp)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_minor(minor: int, currency: str) -> Decimal:
    exp = minor_exponent(currency)
    return (Decimal(minor) / (Decimal(10) ** exp)).quantize(Decimal(1).scaleb(-exp))


def detect_currency(text: str, default: str | None = None) -> str | None:
    upper = text.upper()
    for token, code in _SYMBOLS:
        if token in upper:
            return code
    return default


def parse_number(raw: str) -> Decimal | None:
    """Parse '1,250.50', '1.250,50', '1 250', '৳১,২৫০' → Decimal. Returns None if not a number."""
    s = raw.translate(_BN_DIGITS)
    m = _NUMBER.search(s)
    if not m:
        return None
    s = re.sub(r"[\s  ']", "", m.group(0)).rstrip(".,")
    if not s:
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        # whichever separator appears last is the decimal separator
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        head, _, tail = s.rpartition(",")
        # "1,250" (thousands) vs "2,99" (decimal comma): 3 trailing digits ⇒ thousands
        if len(tail) == 3 and head.replace(",", "").isdigit():
            s = s.replace(",", "")
        elif s.count(",") == 1:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def parse_price(text: str, default_currency: str | None = None) -> tuple[Decimal, str | None] | None:
    amount = parse_number(text)
    if amount is None:
        return None
    return amount, detect_currency(text, default_currency)
