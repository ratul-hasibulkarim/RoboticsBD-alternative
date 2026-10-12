"""Keyword-based category assignment for new components (editable later in the admin console)."""

from __future__ import annotations

import re

# (category, subcategory, pattern) — first match wins; checked against title + category hint.
_RULES: list[tuple[str, str | None, str]] = [
    ("dev-board", "arduino", r"\barduino (uno|nano|mega|pro mini|leonardo|due)\b|\bnodemcu\b|\bwemos\b"),
    ("dev-board", "raspberry-pi", r"\braspberry pi\b|\brpi\b|\bpico\b"),
    ("dev-board", "esp", r"\besp32[- ]?(devkit|dev kit|dev board|cam)|\besp8266 (dev|board)"),
    ("wireless", "wifi-ble", r"\besp32\b|\besp-?32|\besp8266\b|\besp-?01\b|\bwroom\b|\bwrover\b|\bnrf24|\bnrf52"),
    ("wireless", "lora", r"\blora\b|\bsx127\d|\brfm9\d"),
    ("wireless", "gsm-gps", r"\bsim800|\bsim900|\bneo-?6m|\bgps\b|\bgsm\b"),
    ("mcu", "avr", r"\batmega|\battiny|\bavr\b"),
    ("mcu", "arm", r"\bstm32|\bsamd\d|\brp2040\b|\bnrf5\d|\bcortex"),
    ("mcu", "pic", r"\bpic\d{2}"),
    ("mcu", None, r"\bmicrocontroller\b|\bmcu\b"),
    (
        "sensor",
        "environment",
        r"\bdht\d\d|\bam2302|\bbme\d{3}|\bbmp\d{3}|\bds18b20|\bsht\d\d|\baht\d\d"
        r"|humidity|temperature sensor|pressure sensor",
    ),
    ("sensor", "distance", r"\bhc-?sr04|\bultrasonic|\bvl53l|\btof\b|\blidar"),
    ("sensor", "motion", r"\bmpu-?\d{4}|\bgy-?\d+|\baccelerometer|\bgyro|\bpir\b|\bhc-?sr501|\bimu\b"),
    ("sensor", "gas", r"\bmq-?\d+\b|\bgas sensor"),
    ("sensor", None, r"\bsensor\b"),
    ("power", "regulator", r"\blm78\d\d|\b78\d\d\b|\bams1117|\blm317|\bldo\b|\bregulator"),
    ("power", "dc-dc", r"\blm2596|\bmp1584|\bxl\d{4}|\bbuck\b|\bboost\b|\bstep[- ]?(down|up)|\bdc-dc"),
    ("power", "battery-charger", r"\btp4056|\bbms\b|\bcharger\b"),
    ("battery", None, r"\b18650\b|\blipo\b|\bli-?ion\b|\bbattery\b|\bcell\b"),
    ("ic-analog", "timer", r"\bne555|\b555 timer|\blm555|\bne556"),
    ("ic-analog", "op-amp", r"\blm358|\blm324|\blm741|\bua741|\btl07\d|\bop-?amp|\boperational amplifier"),
    ("ic-logic", "shift-register", r"\b74hc595|\b74hc165|\bshift register"),
    ("ic-logic", None, r"\b74(hc|hct|ls|lvc)\d+|\bcd40\d\d"),
    ("ic-interface", "usb-uart", r"\bch340|\bcp210\d|\bft232|\bpl2303|\busb to (ttl|serial|uart)"),
    ("motor-driver", None, r"\bl298|\bl293|\bdrv88\d\d|\ba4988|\btb6612|\bmotor driver"),
    ("motor", None, r"\bservo\b|\bsg90\b|\bmg996|\bstepper\b|\bnema\s?17|\bdc motor|\bgear motor"),
    (
        "display",
        None,
        r"\blcd\b|\boled\b|\btft\b|\bssd1306|\b1602\b|\b2004\b|\bst7735|\bili9341|\bseven segment|\b7-segment",
    ),
    ("passive", "resistor", r"\bresistor|\bohm\b|\bpotentiometer|\btrimmer"),
    ("passive", "capacitor", r"\bcapacitor|\b\d+(\.\d+)?\s?(uf|µf|nf|pf)\b"),
    ("passive", "inductor", r"\binductor|\b\d+\s?(uh|µh|mh)\b"),
    ("semiconductor", "transistor", r"\btransistor|\bbc\d{3}\b|\b2n\d{4}|\btip\d{2,3}|\bs8050|\bs8550"),
    ("semiconductor", "mosfet", r"\bmosfet|\birf[zl]?\d{3,4}|\bao\d{4}"),
    ("semiconductor", "diode", r"\bdiode|\b1n\d{4}|\bzener|\bschottky|\bled\b"),
    ("connector", None, r"\bheader\b|\bconnector|\bjumper wire|\bdupont|\bjst\b|\bterminal block"),
    ("relay", None, r"\brelay\b"),
    ("tool", None, r"\bsoldering|\bmultimeter|\bbreadboard|\boscilloscope|\bwire stripper"),
]
_COMPILED = [(c, s, re.compile(p, re.IGNORECASE)) for c, s, p in _RULES]


def categorize(title: str, hint: str | None = None) -> tuple[str, str | None]:
    text = f"{title} {hint or ''}"
    for cat, sub, rx in _COMPILED:
        if rx.search(text):
            return cat, sub
    return "other", None


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "part"
