#!/usr/bin/env python3
"""Seed a runnable demo (E1): 500 REAL part numbers with SYNTHETIC demo prices.

* Part numbers, manufacturers, packages and key specs are real catalogue parts.
* Offers come from four clearly-labelled demo sources ("Demo …", *.test domains) with
  deterministic synthetic prices — this is not market data and must never be deployed as such.
* Indexes into Typesense when it is reachable (otherwise the API's Postgres search is used).

    python scripts/seed_demo_data.py --components 500
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from api.tests.factory import FX_RATES, add_component, add_offer, add_sources
from common.db import session_scope
from common.models import Component, UseCase
from price.fx import FxTable, store_rates

# (mpn, manufacturer, title, package, specs, base_usd)
Part = tuple[str, str, str, str | None, dict[str, str], float]

CORE: list[Part] = [
    (
        "ESP32-WROOM-32E",
        "Espressif",
        "ESP32-WROOM-32E Wi-Fi + Bluetooth module",
        "SMD-38",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "240MHz"},
        3.2,
    ),
    (
        "ESP32-WROOM-32D",
        "Espressif",
        "ESP32-WROOM-32D Wi-Fi + Bluetooth module",
        "SMD-38",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "240MHz"},
        3.0,
    ),
    (
        "ESP32-C3-MINI-1",
        "Espressif",
        "ESP32-C3 RISC-V Wi-Fi + BLE module",
        "SMD-53",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "160MHz"},
        2.1,
    ),
    (
        "ESP32-S3-WROOM-1",
        "Espressif",
        "ESP32-S3 Wi-Fi + BLE module",
        "SMD-41",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "8MB", "CPU Frequency": "240MHz"},
        3.9,
    ),
    (
        "ESP-12F",
        "Ai-Thinker",
        "ESP8266 ESP-12F Wi-Fi module",
        "SMD-22",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB"},
        1.6,
    ),
    (
        "ATMEGA328P-PU",
        "Microchip",
        "ATmega328P 8-bit AVR microcontroller",
        "DIP-28",
        {"Flash": "32KB", "Clock Speed": "20MHz", "Operating Voltage": "1.8V ~ 5.5V"},
        2.6,
    ),
    (
        "ATMEGA328P-AU",
        "Microchip",
        "ATmega328P 8-bit AVR microcontroller SMD",
        "TQFP-32",
        {"Flash": "32KB", "Clock Speed": "20MHz", "Operating Voltage": "1.8V ~ 5.5V"},
        2.1,
    ),
    (
        "ATMEGA2560-16AU",
        "Microchip",
        "ATmega2560 8-bit AVR microcontroller",
        "TQFP-100",
        {"Flash": "256KB", "Clock Speed": "16MHz"},
        12.5,
    ),
    (
        "ATTINY85-20PU",
        "Microchip",
        "ATtiny85 8-bit AVR microcontroller",
        "DIP-8",
        {"Flash": "8KB", "Clock Speed": "20MHz"},
        1.4,
    ),
    (
        "STM32F103C8T6",
        "STMicroelectronics",
        "STM32F103 ARM Cortex-M3 microcontroller",
        "LQFP-48",
        {"Flash": "64KB", "Clock Speed": "72MHz"},
        2.9,
    ),
    (
        "STM32F411CEU6",
        "STMicroelectronics",
        "STM32F411 ARM Cortex-M4 microcontroller",
        "UFQFPN-48",
        {"Flash": "512KB", "Clock Speed": "100MHz"},
        4.8,
    ),
    (
        "RP2040",
        "Raspberry Pi",
        "RP2040 dual-core ARM Cortex-M0+ microcontroller",
        "QFN-56",
        {"Clock Speed": "133MHz", "RAM": "264KB"},
        0.8,
    ),
    (
        "CH340G",
        "WCH",
        "CH340G USB to serial UART IC",
        "SOP-16",
        {"Supply Voltage": "3.3V ~ 5V", "Interface": "USB"},
        0.35,
    ),
    (
        "CH340C",
        "WCH",
        "CH340C USB to UART IC (built-in clock)",
        "SOP-16",
        {"Supply Voltage": "3.3V ~ 5V", "Interface": "USB"},
        0.4,
    ),
    (
        "CP2102N-A02-GQFN28",
        "Silicon Labs",
        "CP2102N USB to UART bridge",
        "QFN-28",
        {"Supply Voltage": "3.0V ~ 3.6V", "Interface": "USB"},
        1.9,
    ),
    (
        "FT232RL",
        "FTDI",
        "FT232RL USB to serial UART IC",
        "SSOP-28",
        {"Supply Voltage": "3.3V ~ 5.25V", "Interface": "USB"},
        4.5,
    ),
    (
        "NE555P",
        "Texas Instruments",
        "NE555 precision timer IC",
        "DIP-8",
        {"Supply Voltage": "4.5V ~ 16V", "Frequency": "100kHz"},
        0.48,
    ),
    ("NE556N", "Texas Instruments", "NE556 dual precision timer", "DIP-14", {"Supply Voltage": "4.5V ~ 16V"}, 0.72),
    (
        "LM358N",
        "Texas Instruments",
        "LM358 dual operational amplifier",
        "DIP-8",
        {"Channels": "2", "Supply Voltage": "3V ~ 32V"},
        0.35,
    ),
    (
        "LM358DR",
        "Texas Instruments",
        "LM358 dual op-amp SMD",
        "SOIC-8",
        {"Channels": "2", "Supply Voltage": "3V ~ 32V"},
        0.3,
    ),
    (
        "LM324N",
        "Texas Instruments",
        "LM324 quad operational amplifier",
        "DIP-14",
        {"Channels": "4", "Supply Voltage": "3V ~ 32V"},
        0.42,
    ),
    (
        "TL072CP",
        "Texas Instruments",
        "TL072 dual JFET-input op-amp",
        "DIP-8",
        {"Channels": "2", "Supply Voltage": "±18V"},
        0.55,
    ),
    (
        "LM2596S-ADJ",
        "Texas Instruments",
        "LM2596 3A step-down buck regulator",
        "TO-263-5",
        {"Input Voltage": "4.5V-40V", "Output Current": "3A", "Switching Frequency": "150kHz"},
        2.4,
    ),
    (
        "LM2596T-ADJ",
        "Texas Instruments",
        "LM2596 3A buck regulator THT",
        "TO-220-5",
        {"Input Voltage": "4.5V-40V", "Output Current": "3A"},
        2.8,
    ),
    (
        "MP1584EN-LF-Z",
        "Monolithic Power Systems",
        "MP1584 3A step-down converter",
        "SOIC-8",
        {"Input Voltage": "4.5V-28V", "Output Current": "3A"},
        0.9,
    ),
    (
        "XL6009E1",
        "XLSEMI",
        "XL6009 4A boost converter IC",
        "TO-263-5",
        {"Input Voltage": "5V-32V", "Output Current": "4A"},
        0.6,
    ),
    (
        "AMS1117-3.3",
        "Advanced Monolithic Systems",
        "AMS1117 3.3V 1A LDO regulator",
        "SOT-223",
        {"Output Voltage": "3.3V", "Output Current": "1A"},
        0.12,
    ),
    (
        "AMS1117-5.0",
        "Advanced Monolithic Systems",
        "AMS1117 5V 1A LDO regulator",
        "SOT-223",
        {"Output Voltage": "5V", "Output Current": "1A"},
        0.12,
    ),
    (
        "LM317T",
        "STMicroelectronics",
        "LM317 adjustable voltage regulator",
        "TO-220",
        {"Output Voltage": "1.25V-37V", "Output Current": "1.5A"},
        0.45,
    ),
    (
        "TP4056",
        "Nanjing Top Power",
        "TP4056 1A Li-ion battery charger IC",
        "SOP-8",
        {"Input Voltage": "4V-8V", "Output Current": "1A"},
        0.15,
    ),
    (
        "DHT11",
        "Aosong",
        "DHT11 temperature & humidity sensor",
        None,
        {"Operating Voltage": "3.3-5.5V", "Measuring Range": "0 to 50 °C"},
        0.9,
    ),
    (
        "DHT22",
        "Aosong",
        "DHT22 / AM2302 temperature & humidity sensor",
        None,
        {"Operating Voltage": "3.3-6V", "Measuring Range": "-40 to 80 °C"},
        3.2,
    ),
    (
        "BME280",
        "Bosch Sensortec",
        "BME280 pressure, humidity & temperature sensor",
        "LGA-8",
        {"Supply Voltage": "1.71V ~ 3.6V", "Interface": "I2C/SPI"},
        3.8,
    ),
    (
        "BMP280",
        "Bosch Sensortec",
        "BMP280 barometric pressure sensor",
        "LGA-8",
        {"Supply Voltage": "1.71V ~ 3.6V", "Interface": "I2C/SPI"},
        1.6,
    ),
    (
        "MPU-6050",
        "TDK InvenSense",
        "MPU-6050 6-axis gyro + accelerometer",
        "QFN-24",
        {"Supply Voltage": "2.375V ~ 3.46V", "Interface": "I2C"},
        2.2,
    ),
    (
        "DS18B20",
        "Analog Devices",
        "DS18B20 1-Wire digital temperature sensor",
        "TO-92",
        {"Supply Voltage": "3V ~ 5.5V", "Measuring Range": "-55 to 125 °C"},
        1.9,
    ),
    (
        "HC-SR04",
        "",
        "HC-SR04 ultrasonic distance sensor module",
        None,
        {"Operating Voltage": "5V", "Range": "2cm-400cm"},
        0.9,
    ),
    ("HC-SR501", "", "HC-SR501 PIR motion sensor module", None, {"Operating Voltage": "4.5V-20V"}, 0.8),
    ("MQ-2", "Hanwei", "MQ-2 smoke & combustible gas sensor", None, {"Operating Voltage": "5V"}, 1.1),
    (
        "L298N",
        "STMicroelectronics",
        "L298N dual full-bridge motor driver",
        "Multiwatt-15",
        {"Supply Voltage": "4.5V ~ 46V", "Output Current": "2A"},
        2.4,
    ),
    (
        "L293D",
        "STMicroelectronics",
        "L293D quad half-H motor driver",
        "DIP-16",
        {"Supply Voltage": "4.5V ~ 36V", "Output Current": "600mA"},
        1.3,
    ),
    (
        "A4988SETTR-T",
        "Allegro",
        "A4988 microstepping motor driver",
        "QFN-28",
        {"Supply Voltage": "8V ~ 35V", "Output Current": "2A"},
        2.7,
    ),
    (
        "DRV8825PWPR",
        "Texas Instruments",
        "DRV8825 stepper motor driver",
        "HTSSOP-28",
        {"Supply Voltage": "8.2V ~ 45V", "Output Current": "2.5A"},
        3.9,
    ),
    (
        "TB6612FNG",
        "Toshiba",
        "TB6612FNG dual DC motor driver",
        "SSOP-24",
        {"Supply Voltage": "2.5V ~ 13.5V", "Output Current": "1.2A"},
        2.3,
    ),
    (
        "ULN2003A",
        "Texas Instruments",
        "ULN2003A Darlington transistor array",
        "DIP-16",
        {"Channels": "7", "Output Current": "500mA"},
        0.4,
    ),
    (
        "MAX7219CNG",
        "Analog Devices",
        "MAX7219 8-digit LED display driver",
        "DIP-24",
        {"Supply Voltage": "4V ~ 5.5V", "Interface": "SPI"},
        6.5,
    ),
    (
        "PCF8574N",
        "Texas Instruments",
        "PCF8574 I2C 8-bit I/O expander",
        "DIP-16",
        {"Supply Voltage": "2.5V ~ 6V", "Interface": "I2C"},
        1.5,
    ),
    (
        "SSD1306",
        "Solomon Systech",
        "SSD1306 128x64 OLED display driver",
        None,
        {"Interface": "I2C/SPI", "Resolution": "128x64"},
        1.9,
    ),
    ("SG90", "TowerPro", "SG90 9g micro servo motor", None, {"Operating Voltage": "4.8V-6V"}, 1.4),
    (
        "IRFZ44NPBF",
        "Infineon",
        "IRFZ44N N-channel power MOSFET 55V 49A",
        "TO-220",
        {"Current": "49A", "Voltage": "55V"},
        0.9,
    ),
    (
        "IRLZ44NPBF",
        "Infineon",
        "IRLZ44N logic-level N-channel MOSFET",
        "TO-220",
        {"Current": "47A", "Voltage": "55V"},
        1.1,
    ),
    (
        "IRF540NPBF",
        "Infineon",
        "IRF540N N-channel MOSFET 100V 33A",
        "TO-220",
        {"Current": "33A", "Voltage": "100V"},
        0.95,
    ),
    ("1N4007", "Vishay", "1N4007 1A 1000V rectifier diode", "DO-41", {"Current": "1A", "Voltage": "1000V"}, 0.03),
    ("1N4148", "Vishay", "1N4148 small-signal switching diode", "DO-35", {"Current": "300mA", "Voltage": "100V"}, 0.02),
    ("1N5819", "Vishay", "1N5819 1A 40V Schottky diode", "DO-41", {"Current": "1A", "Voltage": "40V"}, 0.05),
    ("BC547B", "onsemi", "BC547B NPN transistor", "TO-92", {"Current": "100mA", "Voltage": "45V"}, 0.04),
    ("BC557B", "onsemi", "BC557B PNP transistor", "TO-92", {"Current": "100mA", "Voltage": "45V"}, 0.04),
    (
        "2N2222A",
        "STMicroelectronics",
        "2N2222A NPN switching transistor",
        "TO-92",
        {"Current": "600mA", "Voltage": "40V"},
        0.08,
    ),
    (
        "2N3904",
        "onsemi",
        "2N3904 NPN general-purpose transistor",
        "TO-92",
        {"Current": "200mA", "Voltage": "40V"},
        0.04,
    ),
    (
        "TIP120",
        "STMicroelectronics",
        "TIP120 NPN Darlington transistor",
        "TO-220",
        {"Current": "5A", "Voltage": "60V"},
        0.45,
    ),
]

E24 = [
    1.0,
    1.1,
    1.2,
    1.3,
    1.5,
    1.6,
    1.8,
    2.0,
    2.2,
    2.4,
    2.7,
    3.0,
    3.3,
    3.6,
    3.9,
    4.3,
    4.7,
    5.1,
    5.6,
    6.2,
    6.8,
    7.5,
    8.2,
    9.1,
]


def yageo_code(ohms: float) -> str:
    """Yageo RC-series value code: 4.7Ω → 4R7, 470Ω → 470R, 4.7kΩ → 4K7, 1MΩ → 1M."""
    for div, letter in ((1_000_000, "M"), (1000, "K"), (1, "R")):
        if ohms >= div:
            v = round(ohms / div, 3)
            whole, _, frac = f"{v:g}".partition(".")
            return f"{whole}{letter}{frac}"
    return f"{ohms:g}R"


def human_ohms(ohms: float) -> str:
    for div, unit in ((1_000_000, "MΩ"), (1000, "kΩ"), (1, "Ω")):
        if ohms >= div:
            return f"{ohms / div:g}{unit}"
    return f"{ohms:g}Ω"


def resistors() -> list[Part]:
    out: list[Part] = []
    for size, power in (("0805", "0.125W"), ("0603", "0.1W")):
        values = [round(base * decade, 3) for decade in (1, 10, 100, 1_000, 10_000, 100_000) for base in E24] + [
            1_000_000
        ]
        for ohms in values:
            code = yageo_code(ohms)
            title = f"{human_ohms(ohms)} ({code}) 1% {power} {size} thick-film resistor"
            out.append(
                (
                    f"RC{size}FR-07{code}L",
                    "Yageo",
                    title,
                    size,
                    {"Resistance": f"{ohms:g}Ω", "Tolerance": "±1%", "Power": power},
                    0.01,
                )
            )
    return out


def capacitors() -> list[Part]:
    codes = {
        "101": "100pF",
        "221": "220pF",
        "471": "470pF",
        "102": "1nF",
        "222": "2.2nF",
        "472": "4.7nF",
        "103": "10nF",
        "223": "22nF",
        "473": "47nF",
        "104": "100nF",
        "224": "220nF",
        "474": "470nF",
        "105": "1µF",
    }
    return [
        (
            f"CC0805KRX7R9BB{c}",
            "Yageo",
            f"{v} 50V X7R 0805 MLCC capacitor",
            "0805",
            {"Capacitance": v, "Voltage": "50V", "Tolerance": "±10%"},
            0.01,
        )
        for c, v in codes.items()
    ]


def zeners() -> list[Part]:
    volts = [
        3.3,
        3.6,
        3.9,
        4.3,
        4.7,
        5.1,
        5.6,
        6.2,
        6.8,
        7.5,
        8.2,
        9.1,
        10,
        11,
        12,
        13,
        15,
        16,
        18,
        20,
        22,
        24,
        27,
        30,
        33,
        36,
        39,
        43,
        47,
        51,
        56,
        62,
        68,
        75,
        82,
        91,
        100,
    ]
    return [
        (
            f"1N{4728 + i}A",
            "Vishay",
            f"1N{4728 + i}A {v}V 1W Zener diode",
            "DO-41",
            {"Voltage": f"{v}V", "Power": "1W"},
            0.04,
        )
        for i, v in enumerate(volts)
    ]


def logic() -> list[Part]:
    hc = [
        "00",
        "02",
        "04",
        "08",
        "14",
        "20",
        "32",
        "74",
        "86",
        "107",
        "112",
        "123",
        "125",
        "126",
        "132",
        "138",
        "139",
        "151",
        "153",
        "157",
        "161",
        "163",
        "164",
        "165",
        "166",
        "173",
        "174",
        "175",
        "191",
        "193",
        "221",
        "237",
        "238",
        "240",
        "244",
        "245",
        "251",
        "253",
        "257",
        "259",
        "273",
        "299",
        "365",
        "367",
        "373",
        "374",
        "390",
        "393",
        "540",
        "541",
        "573",
        "574",
        "595",
        "4017",
        "4020",
        "4040",
        "4046",
        "4051",
        "4052",
        "4053",
        "4060",
        "4066",
        "4094",
        "4511",
        "4514",
        "4538",
    ]
    out: list[Part] = [
        (
            f"SN74HC{n}N",
            "Texas Instruments",
            f"74HC{n} high-speed CMOS logic IC",
            "DIP-16" if len(n) > 2 else "DIP-14",
            {"Supply Voltage": "2V ~ 6V"},
            0.35,
        )
        for n in hc
    ]
    cd = [
        "4001",
        "4011",
        "4013",
        "4017",
        "4020",
        "4022",
        "4026",
        "4027",
        "4029",
        "4040",
        "4049",
        "4050",
        "4051",
        "4052",
        "4053",
        "4060",
        "4066",
        "4069",
        "4070",
        "4071",
        "4081",
        "4093",
        "4511",
        "4518",
        "4543",
    ]
    out += [
        (f"CD{n}BE", "Texas Instruments", f"CD{n}B CMOS logic IC", "DIP-16", {"Supply Voltage": "3V ~ 18V"}, 0.4)
        for n in cd
    ]
    return out


def regulators() -> list[Part]:
    out: list[Part] = []
    for v in ("05", "06", "08", "09", "12", "15", "18", "24"):
        out.append(
            (
                f"L78{v}CV",
                "STMicroelectronics",
                f"L78{v} {int(v)}V 1.5A positive regulator",
                "TO-220",
                {"Output Voltage": f"{int(v)}V", "Output Current": "1.5A"},
                0.3,
            )
        )
        out.append(
            (
                f"L79{v}CV",
                "STMicroelectronics",
                f"L79{v} -{int(v)}V 1.5A negative regulator",
                "TO-220",
                {"Output Voltage": f"-{int(v)}V", "Output Current": "1.5A"},
                0.35,
            )
        )
    for v, code in (("1.8", "18"), ("2.5", "25"), ("3.3", "33"), ("5.0", "50")):
        out.append(
            (
                f"LD1117V{code}",
                "STMicroelectronics",
                f"LD1117 {v}V 800mA LDO",
                "TO-220",
                {"Output Voltage": f"{v}V"},
                0.4,
            )
        )
    return out


def catalogue() -> list[Part]:
    seen: set[str] = set()
    out: list[Part] = []
    for p in CORE + logic() + regulators() + zeners() + capacitors() + resistors():
        if p[0] not in seen:
            seen.add(p[0])
            out.append(p)
    return out


async def seed(n: int, *, reset: bool) -> int:
    rng = random.Random(1011)
    now = datetime.now(UTC)
    parts = catalogue()[:n]
    if len(parts) < n:
        raise SystemExit(f"catalogue has only {len(parts)} parts")
    async with session_scope() as s:
        if reset:
            from conftest import TABLES

            await s.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await store_rates(s, now.date(), FX_RATES, "demo")
        fx = FxTable(day=now.date(), per_usd=dict(FX_RATES))
        src = await add_sources(s)
        bdt = float(FX_RATES["BDT"])
        for i, (mpn, mfr, title, pkg, specs, usd) in enumerate(parts):
            comp = await add_component(s, mpn, mfr or None, title, specs, package=pkg, popularity=float(len(parts) - i))
            # BD shops: import cost + margin, rounded to whole taka; global distributor: base price.
            for name, markup in (("demo-robotics-bd", 1.35), ("demo-techshop-bd", 1.45), ("demo-ctg-parts", 1.4)):
                if rng.random() < 0.75:
                    taka = max(1, round(usd * bdt * markup * rng.uniform(0.9, 1.1)))
                    await add_offer(
                        s,
                        fx,
                        src[name],
                        comp,
                        Decimal(taka),
                        "BDT",
                        in_stock=rng.random() > 0.12,
                        observed=now - timedelta(hours=rng.uniform(0.5, 72)),
                    )
            await add_offer(
                s,
                fx,
                src["demo-global-dist"],
                comp,
                Decimal(str(round(usd * rng.uniform(0.95, 1.05), 4))),
                "USD",
                ships_from="US",
                ships_to=("*",),
                observed=now - timedelta(hours=rng.uniform(1, 30)),
            )
        esp = (await s.execute(select(Component).where(Component.slug == "esp32-wroom-32e"))).scalar_one()
        s.add(
            UseCase(
                component_id=esp.id,
                slug="blink-led-arduino",
                title="Blink an LED with ESP32 (Arduino core)",
                difficulty="beginner",
                summary="Install the ESP32 Arduino core, then toggle GPIO2 every 500 ms.",
                steps=["Install the ESP32 board package", "Select 'ESP32 Dev Module'", "Upload the sketch"],
                code_language="arduino",
                code_snippet=(
                    "void setup(){ pinMode(2, OUTPUT); }\nvoid loop(){ digitalWrite(2, !digitalRead(2)); delay(500); }"
                ),
                code_license="CC0-1.0",
                source_type="editorial",
                source_url="https://voltfind.com/guides/esp32-blink",
                source_author="VoltFind",
            )
        )
    try:
        from common.db import get_sessionmaker
        from search.indexer import ensure_schema, index_components, typesense_client

        ts = typesense_client()
        await ensure_schema(ts)
        async with get_sessionmaker()() as s:
            indexed = await index_components(s, ts)
        await ts.aclose()
        print(f"indexed {indexed} components in Typesense")
    except Exception as exc:  # Typesense optional for the demo
        print(f"Typesense not indexed ({exc.__class__.__name__}); API falls back to Postgres search")
    return len(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--components", type=int, default=500)
    ap.add_argument("--no-reset", action="store_true", help="append instead of truncating all tables first")
    args = ap.parse_args()
    n = asyncio.run(seed(args.components, reset=not args.no_reset))
    print(f"seeded {n} components with synthetic demo offers")


if __name__ == "__main__":
    main()
