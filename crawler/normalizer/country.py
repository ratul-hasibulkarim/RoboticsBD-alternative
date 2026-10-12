"""Country names / codes → ISO 3166-1 alpha-2."""

from __future__ import annotations

import re

_COUNTRIES: dict[str, str] = {
    "bangladesh": "BD",
    "bd": "BD",
    "বাংলাদেশ": "BD",
    "india": "IN",
    "in": "IN",
    "pakistan": "PK",
    "pk": "PK",
    "nepal": "NP",
    "np": "NP",
    "sri lanka": "LK",
    "lk": "LK",
    "bhutan": "BT",
    "myanmar": "MM",
    "china": "CN",
    "cn": "CN",
    "prc": "CN",
    "people's republic of china": "CN",
    "hong kong": "HK",
    "hk": "HK",
    "taiwan": "TW",
    "tw": "TW",
    "japan": "JP",
    "jp": "JP",
    "south korea": "KR",
    "korea": "KR",
    "kr": "KR",
    "singapore": "SG",
    "sg": "SG",
    "malaysia": "MY",
    "my": "MY",
    "thailand": "TH",
    "th": "TH",
    "vietnam": "VN",
    "viet nam": "VN",
    "vn": "VN",
    "indonesia": "ID",
    "philippines": "PH",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "canada": "CA",
    "ca": "CA",
    "mexico": "MX",
    "united kingdom": "GB",
    "uk": "GB",
    "gb": "GB",
    "great britain": "GB",
    "england": "GB",
    "germany": "DE",
    "de": "DE",
    "france": "FR",
    "fr": "FR",
    "netherlands": "NL",
    "nl": "NL",
    "italy": "IT",
    "spain": "ES",
    "poland": "PL",
    "sweden": "SE",
    "ireland": "IE",
    "switzerland": "CH",
    "australia": "AU",
    "au": "AU",
    "new zealand": "NZ",
    "united arab emirates": "AE",
    "uae": "AE",
    "ae": "AE",
    "saudi arabia": "SA",
    "worldwide": "*",
    "global": "*",
    "international": "*",
}


def to_iso2(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"\s+", " ", raw.strip().lower()).strip(".")
    if key in _COUNTRIES:
        return _COUNTRIES[key]
    if re.fullmatch(r"[a-z]{2}", key):
        return key.upper()
    return None
