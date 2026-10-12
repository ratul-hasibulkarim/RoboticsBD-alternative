"""Spec value and key normalisation.

`normalize_specs` returns two dicts:
  * human:   {"Supply voltage": "3.0–3.6 V"}            — shown in the UI
  * machine: {"supply_voltage": {"min": 3.0, "max": 3.6, "unit": "V"}} — for filters/compare
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_SI_PREFIX = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# canonical unit → accepted spellings (case-sensitive where SI prefixes collide)
_UNITS: dict[str, tuple[str, ...]] = {
    "V": ("V", "v", "volt", "volts", "VDC", "VAC", "Vdc"),
    "A": ("A", "amp", "amps", "ampere"),
    "W": ("W", "watt", "watts"),
    "Hz": ("Hz", "hz", "HZ"),
    "F": ("F",),
    "Ω": ("Ω", "ohm", "ohms", "Ohm", "R", "Ω"),
    "H": ("H",),
    "B": ("B", "byte", "bytes", "Byte"),
    "bit": ("bit", "bits", "b"),
    "°C": ("°C", "℃", "degC", "C"),
    "m": ("m",),
    "g": ("g",),
    "mAh": ("mAh",),
}
_UNIT_LOOKUP = {spelling: canon for canon, spellings in _UNITS.items() for spelling in spellings}

_VALUE = re.compile(
    r"(?P<num>[-+]?\d+(?:[.,]\d+)?)\s*(?P<prefix>[pnuµμmkKMG]?)(?P<unit>mAh|VDC|VAC|Vdc|Ω|ohms?|Ohm|℃|°C|degC|"
    r"[Vv]olts?|amps?|ampere|watts?|Hz|hz|HZ|bytes?|Byte|bits?|[VAWFHRBgCm])?\b(?!\w)"
)
_RANGE_SEP = re.compile(r"(?<=[0-9A-Za-zµμΩ°℃])\s*(?:~|–|—|\bto\b|-)\s*(?=[-+]?\d)")
_FILLER = re.compile(r"(?:\b(?:to|max|min|typ|typical|approx|dc|ac)\b|[\s~–—()+\-,.:/±])", re.IGNORECASE)


def _is_quantity_text(text: str) -> bool:
    """True when the text is only numbers, units and range filler (so 'SOT-23' is NOT a quantity)."""
    rest = _VALUE.sub("", text)
    return _FILLER.sub("", rest) == ""


# raw spec label (lower-cased, punctuation stripped) → canonical key
KEY_ALIASES: dict[str, str] = {
    "operating voltage": "supply_voltage",
    "supply voltage": "supply_voltage",
    "input voltage": "input_voltage",
    "voltage supply": "supply_voltage",
    "vcc": "supply_voltage",
    "working voltage": "supply_voltage",
    "voltage": "supply_voltage",
    "output voltage": "output_voltage",
    "output current": "output_current",
    "max output current": "output_current",
    "current": "current",
    "operating current": "supply_current",
    "supply current": "supply_current",
    "power": "power",
    "power rating": "power",
    "frequency": "frequency",
    "clock speed": "clock_frequency",
    "cpu frequency": "clock_frequency",
    "max frequency": "clock_frequency",
    "speed": "clock_frequency",
    "flash": "flash_size",
    "flash memory": "flash_size",
    "program memory size": "flash_size",
    "sram": "ram_size",
    "ram": "ram_size",
    "ram size": "ram_size",
    "data ram size": "ram_size",
    "cores": "cores",
    "number of cores": "cores",
    "core": "core",
    "core processor": "core",
    "package": "package",
    "package case": "package",
    "package / case": "package",
    "packaging": "packaging",
    "mounting type": "mounting",
    "operating temperature": "operating_temperature",
    "temperature range": "operating_temperature",
    "resistance": "resistance",
    "capacitance": "capacitance",
    "inductance": "inductance",
    "tolerance": "tolerance",
    "interface": "interface",
    "communication interface": "interface",
    "wireless": "wireless",
    "connectivity": "wireless",
    "gpio": "gpio_count",
    "number of i/o": "gpio_count",
    "i/o pins": "gpio_count",
    "channels": "channels",
    "number of channels": "channels",
    "resolution": "resolution",
    "accuracy": "accuracy",
    "range": "range",
    "measuring range": "range",
    "efficiency": "efficiency",
    "switching frequency": "switching_frequency",
    "dimensions": "dimensions",
    "size": "dimensions",
    "weight": "weight",
    "manufacturer": "manufacturer",
    "brand": "manufacturer",
    "model": "model",
    "part number": "mpn",
    "mfr part": "mpn",
    "mpn": "mpn",
}


def canonical_key(label: str) -> str:
    s = unicodedata.normalize("NFKC", label).strip().lower()
    s = re.sub(r"[:()\[\]*]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s in KEY_ALIASES:
        return KEY_ALIASES[s]
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def parse_quantity(text: str) -> tuple[float, str] | None:
    """'4.7µF' → (4.7e-6, 'F'); '10k' → (10000.0, '') ; '3.3V' → (3.3, 'V')."""
    m = _VALUE.search(unicodedata.normalize("NFKC", text).replace("Ω", "Ω"))
    if not m:
        return None
    num = float(m.group("num").replace(",", "."))
    prefix = m.group("prefix") or ""
    unit_raw = m.group("unit") or ""
    if unit_raw == "mAh":
        return num, "mAh"
    # "m" alone after a number is metres unless followed by a unit; "M" alone = mega (resistors)
    if not unit_raw and prefix in ("m",):
        return num, "m"
    unit = _UNIT_LOOKUP.get(unit_raw, _UNIT_LOOKUP.get(unit_raw.lower(), unit_raw))
    if unit == "Ω" and unit_raw == "R" and prefix == "":
        unit = "Ω"
    return float(f"{num * _SI_PREFIX.get(prefix, 1.0):.12g}"), unit


def parse_range(text: str) -> dict[str, Any] | None:
    """'3.0V ~ 3.6V' / '-40 to 85 °C' / '2.7-5.5V' → {'min':..,'max':..,'unit':..}."""
    t = unicodedata.normalize("NFKC", text)
    # '1/4W' → '0.25W'
    t = re.sub(r"\b(\d+)/(\d+)(?=\s*[A-Za-zΩ°])", lambda m: f"{int(m[1]) / int(m[2]):g}", t)
    if not _is_quantity_text(t):
        return None
    parts = _RANGE_SEP.split(t, maxsplit=1)
    if len(parts) == 2:
        lo, hi = parse_quantity(parts[0]), parse_quantity(parts[1])
        if lo and hi:
            unit = hi[1] or lo[1]
            lo_v = lo[0]
            # '2.7-5.5V': lower bound inherits the upper bound's unit
            return {"min": min(lo_v, hi[0]), "max": max(lo_v, hi[0]), "unit": unit}
    q = parse_quantity(t)
    if q:
        return {"value": q[0], "unit": q[1]}
    return None


def normalize_specs(raw: dict[str, str]) -> tuple[dict[str, str], dict[str, Any]]:
    human: dict[str, str] = {}
    machine: dict[str, Any] = {}
    for label, value in raw.items():
        if not label or value is None:
            continue
        v = " ".join(str(value).split())
        if not v or len(v) > 200:
            continue
        human[label.strip().rstrip(":")[:80]] = v
        key = canonical_key(label)
        parsed = parse_range(v)
        machine[key] = parsed if parsed else {"text": v.lower()}
    return human, machine


def spec_overlap(a: dict[str, Any], b: dict[str, Any], rel_tol: float = 0.05) -> float:
    """Fraction of shared machine-spec keys whose values agree (used by the resolver, §6.1 step 5).

    Returns 1.0 when there are no shared keys (no evidence of conflict).
    """
    shared = [k for k in a.keys() & b.keys() if k not in ("manufacturer", "model", "mpn")]
    if not shared:
        return 1.0
    agree = 0
    for k in shared:
        x, y = a[k], b[k]
        if "text" in x or "text" in y:
            agree += int(x.get("text") == y.get("text"))
            continue
        if x.get("unit") != y.get("unit"):
            continue
        xv = (x.get("value"), x.get("min"), x.get("max"))
        yv = (y.get("value"), y.get("min"), y.get("max"))
        ok = True
        for p, q in zip(xv, yv, strict=True):
            if p is None and q is None:
                continue
            if p is None or q is None:
                ok = False
                break
            if abs(p - q) > rel_tol * max(abs(p), abs(q), 1e-12):
                ok = False
                break
        agree += int(ok)
    return agree / len(shared)
