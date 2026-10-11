"""Manufacturer part number (MPN) and manufacturer-name normalisation.

Three forms:
  * display  — `normalize_mpn`: upper-case, trimmed, unicode dashes unified. Stored in components.mpn.
  * key      — `mpn_key`: lower-case alphanumerics only. Stored in components.mpn_norm.
  * matching — `mpn_match_key`: key with distributor packaging suffixes removed. NEVER stored.
"""

from __future__ import annotations

import re
import unicodedata

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣－"), "-")
_SLASHES = dict.fromkeys(map(ord, "⁄∕／"), "/")

# Distributor packaging / ordering suffixes. Matched on the display form, end-anchored.
_PACKAGING_SUFFIXES = re.compile(
    r"(?:[-/ ](?:ND|CT|TR|DKR|REEL|TAPE|T&R|CUT ?TAPE|BULK|TUBE|TRAY)|#?PBF|-?E3|-?G4|-?NOPB)+$",
    re.IGNORECASE,
)

# Tokens that look like part numbers but are values, sizes or marketing.
_NOT_MPN = re.compile(
    r"^(?:\d+(?:\.\d+)?(?:V|MV|KV|A|MA|UA|W|MW|KW|HZ|KHZ|MHZ|GHZ|F|PF|NF|UF|µF|MF|R|K|KΩ|Ω|OHM|M|MM|CM|"
    r"MAH|AH|DB|DBM|C|°C|BIT|BITS|MB|KB|GB|PCS|PC|PIN|PINS|CH|X)"
    r"|\d+/\d+[A-Z]*|\d+X\d+(?:X\d+)?|[A-Z]{1,3}\d?|V\d+(?:\.\d+)*|REV\d*|TYPE-?C|USB\d?(?:\.\d)?|2\.4G|5G|4G|3G|WIFI\d?|"
    r"IP\d{2}|\d{1,2}(?:ST|ND|RD|TH))$",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-./_+#]{2,30}[A-Za-z0-9#+]")

MANUFACTURER_ALIASES: dict[str, str] = {
    "ti": "Texas Instruments",
    "texas instruments": "Texas Instruments",
    "texas instruments inc": "Texas Instruments",
    "st": "STMicroelectronics",
    "stmicro": "STMicroelectronics",
    "stmicroelectronics": "STMicroelectronics",
    "st microelectronics": "STMicroelectronics",
    "microchip": "Microchip",
    "microchip technology": "Microchip",
    "microchip technology inc": "Microchip",
    "atmel": "Microchip",
    "espressif": "Espressif",
    "espressif systems": "Espressif",
    "espressif systems shanghai": "Espressif",
    "nxp": "NXP",
    "nxp semiconductors": "NXP",
    "nxp usa inc": "NXP",
    "onsemi": "onsemi",
    "on semiconductor": "onsemi",
    "on semi": "onsemi",
    "fairchild": "onsemi",
    "fairchild semiconductor": "onsemi",
    "analog devices": "Analog Devices",
    "analog devices inc": "Analog Devices",
    "adi": "Analog Devices",
    "maxim": "Analog Devices",
    "maxim integrated": "Analog Devices",
    "linear technology": "Analog Devices",
    "infineon": "Infineon",
    "infineon technologies": "Infineon",
    "international rectifier": "Infineon",
    "renesas": "Renesas",
    "renesas electronics": "Renesas",
    "raspberry pi": "Raspberry Pi",
    "raspberry pi ltd": "Raspberry Pi",
    "raspberry pi foundation": "Raspberry Pi",
    "arduino": "Arduino",
    "arduino srl": "Arduino",
    "bosch": "Bosch Sensortec",
    "bosch sensortec": "Bosch Sensortec",
    "vishay": "Vishay",
    "vishay intertechnology": "Vishay",
    "diodes": "Diodes Inc",
    "diodes incorporated": "Diodes Inc",
    "diodes inc": "Diodes Inc",
    "wch": "WCH",
    "nanjing qinheng microelectronics": "WCH",
    "aosong": "Aosong",
    "asair": "Aosong",
    "invensense": "TDK InvenSense",
    "tdk invensense": "TDK InvenSense",
    "silicon labs": "Silicon Labs",
    "silicon laboratories": "Silicon Labs",
    "ftdi": "FTDI",
    "future technology devices": "FTDI",
    "nordic": "Nordic Semiconductor",
    "nordic semiconductor": "Nordic Semiconductor",
    "rohm": "ROHM",
    "rohm semiconductor": "ROHM",
    "toshiba": "Toshiba",
    "murata": "Murata",
    "murata electronics": "Murata",
    "yageo": "Yageo",
    "samsung electro-mechanics": "Samsung Electro-Mechanics",
    "hi-link": "Hi-Link",
    "hlk": "Hi-Link",
    "xlsemi": "XLSEMI",
    "generic": "",
    "no brand": "",
    "unbranded": "",
    "oem": "",
    "china": "",
}

_CORP_SUFFIX = re.compile(r"[,.]?\s*\b(inc|incorporated|corp|corporation|co|ltd|limited|llc|gmbh|ag|sa|bv|plc)\b\.?$", re.I)


def normalize_mpn(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw).translate(_DASHES).translate(_SLASHES)
    s = re.sub(r"\s+", " ", s).strip().strip(".,;:")
    return s.upper()


def mpn_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_mpn(raw).lower())


def strip_packaging(raw: str) -> str:
    s = normalize_mpn(raw)
    stripped = _PACKAGING_SUFFIXES.sub("", s)
    return stripped if len(stripped) >= 3 else s


def mpn_match_key(raw: str) -> str:
    return mpn_key(strip_packaging(raw))


def normalize_manufacturer(raw: str | None) -> str:
    """Canonical display name ('' when unknown/generic)."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", raw).strip()
    key = re.sub(r"\s+", " ", _CORP_SUFFIX.sub("", s.lower())).strip(" .,")
    key = re.sub(r"[()]", "", key)
    if key in MANUFACTURER_ALIASES:
        return MANUFACTURER_ALIASES[key]
    return re.sub(r"\s+", " ", _CORP_SUFFIX.sub("", s)).strip(" .,")


def manufacturer_key(raw: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_manufacturer(raw).lower())


def looks_like_mpn(token: str) -> bool:
    t = token.strip()
    if len(t) < 4 or len(t) > 32:
        return False
    if not re.search(r"[A-Za-z]", t) or not re.search(r"\d", t):
        return False
    return not _NOT_MPN.match(t)


def guess_mpn(title: str) -> str | None:
    """Best-effort MPN from a free-text title, e.g. 'LM2596S-ADJ DC-DC Buck Module' → 'LM2596S-ADJ'.

    Returns None when no token is convincing; the resolver then falls back to embeddings.
    """
    candidates: list[tuple[int, int, str]] = []
    for pos, m in enumerate(_TOKEN.finditer(title)):
        tok = m.group(0).strip("-./")
        if not looks_like_mpn(tok):
            continue
        digits = sum(c.isdigit() for c in tok)
        letters = sum(c.isalpha() for c in tok)
        score = min(digits, 6) + min(letters, 6) + (2 if "-" in tok else 0) - pos
        candidates.append((score, -pos, tok))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return normalize_mpn(candidates[0][2])


def levenshtein_le(a: str, b: str, k: int) -> bool:
    from rapidfuzz.distance import Levenshtein

    return bool(Levenshtein.distance(a, b, score_cutoff=k) <= k)
