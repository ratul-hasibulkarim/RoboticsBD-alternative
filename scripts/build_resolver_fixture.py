#!/usr/bin/env python3
"""Build resolver/tests/fixtures/listings_200.json — the R1 evaluation set.

The set is SYNTHETIC BUT REALISTIC: 200 listings generated from 50 real parts using the
title/MPN/manufacturer variations seen on BD shops and global distributors (alias
manufacturer names, typos, missing manufacturer, packaging suffixes, spaced MPNs, MPNs
only in the title, GTINs on distributor listings). Ground truth (`truth`) is known by
construction. It intentionally contains look-alike parts that must NOT be merged:
ESP32-WROOM-32 / -32D / -32E, AMS1117-3.3 / -5.0, ATMEGA328P-PU / -AU / ATMEGA328-PU,
LM358N / LM358DR, IRFZ44N / IRLZ44N, LM7805CT (onsemi) / L7805CV (ST), DHT11 / DHT22,
BME280 / BMP280, MPU-6050 / MPU-6500, CH340G / CH340C, 1N4007 / 1N4148.

Deterministic (seeded). Re-run only when deliberately changing the set.
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "resolver" / "tests" / "fixtures" / "listings_200.json"

# truth_id, mpn, manufacturer, package, description, specs, gtin
PARTS: list[tuple[str, str, str, str | None, str, dict[str, str], str | None]] = [
    (
        "esp32-wroom-32",
        "ESP32-WROOM-32",
        "Espressif",
        "SMD-38",
        "WiFi Bluetooth Module",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "240MHz"},
        None,
    ),
    (
        "esp32-wroom-32d",
        "ESP32-WROOM-32D",
        "Espressif",
        "SMD-38",
        "WiFi BT Module (D revision)",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "CPU Frequency": "240MHz"},
        None,
    ),
    (
        "esp32-wroom-32e",
        "ESP32-WROOM-32E",
        "Espressif",
        "SMD-38",
        "WiFi BT BLE Module ECO V3",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "8MB", "CPU Frequency": "240MHz"},
        None,
    ),
    (
        "esp8266-esp-12f",
        "ESP-12F",
        "Ai-Thinker",
        "SMD-22",
        "ESP8266 WiFi Module",
        {"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB"},
        None,
    ),
    (
        "ams1117-3.3",
        "AMS1117-3.3",
        "Advanced Monolithic Systems",
        "SOT-223",
        "LDO Voltage Regulator 1A",
        {"Output Voltage": "3.3V", "Output Current": "1A", "Input Voltage": "4.5V-15V"},
        None,
    ),
    (
        "ams1117-5.0",
        "AMS1117-5.0",
        "Advanced Monolithic Systems",
        "SOT-223",
        "LDO Voltage Regulator 1A",
        {"Output Voltage": "5V", "Output Current": "1A", "Input Voltage": "6.5V-15V"},
        None,
    ),
    (
        "atmega328p-pu",
        "ATMEGA328P-PU",
        "Microchip",
        "DIP-28",
        "8-bit AVR Microcontroller",
        {"Flash": "32KB", "Clock Speed": "20MHz", "Operating Voltage": "1.8V ~ 5.5V"},
        "0611247012345",
    ),
    (
        "atmega328p-au",
        "ATMEGA328P-AU",
        "Microchip",
        "TQFP-32",
        "8-bit AVR Microcontroller SMD",
        {"Flash": "32KB", "Clock Speed": "20MHz", "Operating Voltage": "1.8V ~ 5.5V"},
        None,
    ),
    (
        "atmega328-pu",
        "ATMEGA328-PU",
        "Microchip",
        "DIP-28",
        "8-bit AVR MCU (non-picoPower)",
        {"Flash": "32KB", "Clock Speed": "20MHz", "Operating Voltage": "1.8V ~ 5.5V"},
        None,
    ),
    (
        "lm358n",
        "LM358N",
        "Texas Instruments",
        "DIP-8",
        "Dual Op-Amp",
        {"Channels": "2", "Supply Voltage": "3V ~ 32V"},
        None,
    ),
    (
        "lm358dr",
        "LM358DR",
        "Texas Instruments",
        "SOIC-8",
        "Dual Operational Amplifier SMD",
        {"Channels": "2", "Supply Voltage": "3V ~ 32V"},
        None,
    ),
    (
        "ne555p",
        "NE555P",
        "Texas Instruments",
        "DIP-8",
        "Precision Timer IC",
        {"Supply Voltage": "4.5V ~ 16V", "Frequency": "100kHz"},
        "0751492000015",
    ),
    (
        "ne555dr",
        "NE555DR",
        "Texas Instruments",
        "SOIC-8",
        "Timer IC SMD",
        {"Supply Voltage": "4.5V ~ 16V", "Frequency": "100kHz"},
        None,
    ),
    (
        "sn74hc595n",
        "SN74HC595N",
        "Texas Instruments",
        "DIP-16",
        "8-bit Shift Register",
        {"Supply Voltage": "2V ~ 6V", "Channels": "8"},
        None,
    ),
    (
        "lm2596s-adj",
        "LM2596S-ADJ",
        "Texas Instruments",
        "TO-263-5",
        "Step-Down Buck Regulator 3A",
        {"Input Voltage": "4.5V-40V", "Output Current": "3A", "Switching Frequency": "150kHz"},
        None,
    ),
    (
        "lm2596t-adj",
        "LM2596T-ADJ",
        "Texas Instruments",
        "TO-220-5",
        "Buck Regulator 3A THT",
        {"Input Voltage": "4.5V-40V", "Output Current": "3A", "Switching Frequency": "150kHz"},
        None,
    ),
    (
        "dht11",
        "DHT11",
        "Aosong",
        None,
        "Temperature and Humidity Sensor",
        {"Operating Voltage": "3.3-5.5V", "Measuring Range": "0 to 50 °C"},
        None,
    ),
    (
        "dht22",
        "DHT22",
        "Aosong",
        None,
        "Digital Temperature Humidity Sensor AM2302",
        {"Operating Voltage": "3.3-6V", "Measuring Range": "-40 to 80 °C"},
        None,
    ),
    (
        "bme280",
        "BME280",
        "Bosch Sensortec",
        "LGA-8",
        "Pressure Humidity Temperature Sensor",
        {"Supply Voltage": "1.71V ~ 3.6V", "Interface": "I2C/SPI"},
        None,
    ),
    (
        "bmp280",
        "BMP280",
        "Bosch Sensortec",
        "LGA-8",
        "Barometric Pressure Sensor",
        {"Supply Voltage": "1.71V ~ 3.6V", "Interface": "I2C/SPI"},
        None,
    ),
    (
        "mpu-6050",
        "MPU-6050",
        "TDK InvenSense",
        "QFN-24",
        "6-Axis Gyro Accelerometer",
        {"Supply Voltage": "2.375V ~ 3.46V", "Interface": "I2C"},
        None,
    ),
    (
        "mpu-6500",
        "MPU-6500",
        "TDK InvenSense",
        "QFN-24",
        "6-Axis Motion Tracking Device",
        {"Supply Voltage": "1.71V ~ 3.6V", "Interface": "I2C/SPI"},
        None,
    ),
    (
        "hc-sr04",
        "HC-SR04",
        "",
        None,
        "Ultrasonic Distance Sensor",
        {"Operating Voltage": "5V", "Range": "2cm-400cm"},
        None,
    ),
    ("hc-sr501", "HC-SR501", "", None, "PIR Motion Sensor", {"Operating Voltage": "4.5V-20V", "Range": "7m"}, None),
    (
        "ch340g",
        "CH340G",
        "WCH",
        "SOP-16",
        "USB to Serial UART IC",
        {"Supply Voltage": "3.3V ~ 5V", "Interface": "USB"},
        None,
    ),
    (
        "ch340c",
        "CH340C",
        "WCH",
        "SOP-16",
        "USB to UART IC (built-in clock)",
        {"Supply Voltage": "3.3V ~ 5V", "Interface": "USB"},
        None,
    ),
    (
        "tp4056",
        "TP4056",
        "Nanjing Top Power",
        "SOP-8",
        "1A Li-ion Battery Charger IC",
        {"Input Voltage": "4V-8V", "Output Current": "1A"},
        None,
    ),
    ("1n4007", "1N4007", "Vishay", "DO-41", "Rectifier Diode 1A 1000V", {"Current": "1A", "Voltage": "1000V"}, None),
    (
        "1n4148",
        "1N4148",
        "Vishay",
        "DO-35",
        "Small Signal Switching Diode",
        {"Current": "300mA", "Voltage": "100V"},
        None,
    ),
    ("1n5819", "1N5819", "Vishay", "DO-41", "Schottky Diode 1A 40V", {"Current": "1A", "Voltage": "40V"}, None),
    ("bc547b", "BC547B", "onsemi", "TO-92", "NPN Transistor", {"Current": "100mA", "Voltage": "45V"}, None),
    (
        "2n2222a",
        "2N2222A",
        "STMicroelectronics",
        "TO-92",
        "NPN Switching Transistor",
        {"Current": "600mA", "Voltage": "40V"},
        None,
    ),
    (
        "irfz44n",
        "IRFZ44N",
        "Infineon",
        "TO-220",
        "N-Channel Power MOSFET 55V 49A",
        {"Current": "49A", "Voltage": "55V", "Gate Threshold Voltage": "2V-4V"},
        None,
    ),
    (
        "irlz44n",
        "IRLZ44N",
        "Infineon",
        "TO-220",
        "Logic Level N-Channel MOSFET",
        {"Current": "47A", "Voltage": "55V", "Gate Threshold Voltage": "1V-2V"},
        None,
    ),
    (
        "irf540n",
        "IRF540N",
        "Infineon",
        "TO-220",
        "N-Channel MOSFET 100V 33A",
        {"Current": "33A", "Voltage": "100V", "Gate Threshold Voltage": "2V-4V"},
        None,
    ),
    (
        "lm7805ct",
        "LM7805CT",
        "onsemi",
        "TO-220",
        "5V Positive Voltage Regulator",
        {"Output Voltage": "5V", "Output Current": "1A"},
        None,
    ),
    (
        "l7805cv",
        "L7805CV",
        "STMicroelectronics",
        "TO-220",
        "5V 1.5A Voltage Regulator",
        {"Output Voltage": "5V", "Output Current": "1.5A"},
        None,
    ),
    (
        "uln2003a",
        "ULN2003A",
        "Texas Instruments",
        "DIP-16",
        "Darlington Transistor Array",
        {"Channels": "7", "Output Current": "500mA"},
        None,
    ),
    (
        "l298n",
        "L298N",
        "STMicroelectronics",
        "Multiwatt-15",
        "Dual Full-Bridge Motor Driver",
        {"Supply Voltage": "4.5V ~ 46V", "Output Current": "2A"},
        None,
    ),
    (
        "a4988",
        "A4988",
        "Allegro",
        "QFN-28",
        "Stepper Motor Driver",
        {"Supply Voltage": "8V ~ 35V", "Output Current": "2A"},
        None,
    ),
    (
        "drv8825",
        "DRV8825",
        "Texas Instruments",
        "HTSSOP-28",
        "Stepper Motor Driver 2.5A",
        {"Supply Voltage": "8.2V ~ 45V", "Output Current": "2.5A"},
        None,
    ),
    (
        "ds18b20",
        "DS18B20",
        "Analog Devices",
        "TO-92",
        "1-Wire Digital Temperature Sensor",
        {"Supply Voltage": "3V ~ 5.5V", "Measuring Range": "-55 to 125 °C"},
        None,
    ),
    ("sg90", "SG90", "TowerPro", None, "9g Micro Servo Motor", {"Operating Voltage": "4.8V-6V"}, None),
    (
        "ssd1306-128x64",
        "SSD1306",
        "Solomon Systech",
        None,
        "0.96 inch OLED Display Driver",
        {"Interface": "I2C/SPI", "Resolution": "128x64"},
        None,
    ),
    (
        "rp2040",
        "RP2040",
        "Raspberry Pi",
        "QFN-56",
        "Dual-core ARM Cortex-M0+ MCU",
        {"Clock Speed": "133MHz", "RAM": "264KB"},
        None,
    ),
    (
        "stm32f103c8t6",
        "STM32F103C8T6",
        "STMicroelectronics",
        "LQFP-48",
        "ARM Cortex-M3 MCU 64KB",
        {"Flash": "64KB", "Clock Speed": "72MHz"},
        None,
    ),
    ("mq-2", "MQ-2", "Hanwei", None, "Smoke Gas Sensor", {"Operating Voltage": "5V"}, None),
    (
        "lm317t",
        "LM317T",
        "STMicroelectronics",
        "TO-220",
        "Adjustable Voltage Regulator 1.5A",
        {"Output Voltage": "1.25V-37V", "Output Current": "1.5A"},
        None,
    ),
    (
        "max7219cng",
        "MAX7219CNG",
        "Analog Devices",
        "DIP-24",
        "LED Display Driver",
        {"Supply Voltage": "4V ~ 5.5V", "Interface": "SPI"},
        None,
    ),
    (
        "pcf8574",
        "PCF8574",
        "NXP",
        "DIP-16",
        "I2C I/O Expander",
        {"Supply Voltage": "2.5V ~ 6V", "Interface": "I2C"},
        None,
    ),
]

MFR_ALIASES = {
    "Texas Instruments": ["Texas Instruments", "TI", "Texas Instruments Inc.", "Texas Instrument"],
    "Microchip": ["Microchip", "Microchip Technology", "Atmel", "Microchip Technology Inc"],
    "STMicroelectronics": ["STMicroelectronics", "ST", "STMicro", "ST Microelectronics"],
    "Espressif": ["Espressif", "Espressif Systems", "ESPRESSIF"],
    "onsemi": ["onsemi", "ON Semiconductor", "ON Semi"],
    "Analog Devices": ["Analog Devices", "Maxim Integrated", "Analog Devices Inc."],
    "Bosch Sensortec": ["Bosch Sensortec", "Bosch"],
    "TDK InvenSense": ["TDK InvenSense", "InvenSense"],
    "Infineon": ["Infineon", "Infineon Technologies", "International Rectifier"],
    "Vishay": ["Vishay", "Vishay Intertechnology"],
    "WCH": ["WCH", "Nanjing Qinheng Microelectronics"],
}

SHOP_TEMPLATES = [
    "{mpn} {desc}",
    "{desc} {mpn}",
    "{mpn} {desc} - {pkg}",
    "{mpn} {pkg} {desc}",
    "Original {mpn} {desc}",
    "{mpn_lower} {desc_lower}",
    "{mpn_nodash} {desc}",
    "{mpn} {desc} (Best Quality)",
]
SPACED_TEMPLATE = "{mpn_spaced} {desc}"
DIST_TEMPLATES = ["{mfr} {mpn} {desc}", "{mpn} - {desc}", "{mpn}, {desc}, {pkg}"]


def _variants(rng: random.Random, part: tuple[Any, ...], n: int) -> list[dict[str, object]]:
    truth, mpn, mfr, pkg, desc, specs, gtin = part
    out = []
    for i in range(n):
        distributor = i == 0 or rng.random() < 0.4  # every part has ≥1 distributor listing
        fill = {
            "mpn": mpn,
            "mpn_lower": mpn.lower(),
            "mpn_nodash": mpn.replace("-", ""),
            "mpn_spaced": mpn.replace("-", " "),
            "desc": desc,
            "desc_lower": desc.lower(),
            "pkg": pkg or "Module",
            "mfr": mfr or "Generic",
        }
        if distributor:
            title = rng.choice(DIST_TEMPLATES).format(**fill)
            listing_mpn: str | None = mpn
            if pkg and pkg.startswith(("SOIC", "SOP", "QFN", "TQFP", "LQFP", "SOT", "HTSSOP")) and rng.random() < 0.4:
                listing_mpn = mpn + rng.choice(["-TR", "/TR", "-CT"])  # packaging suffix
            manufacturer: str | None = rng.choice(MFR_ALIASES.get(mfr, [mfr])) if mfr else None
            listing_gtin = gtin if gtin and rng.random() < 0.7 else None
            spec_subset = dict(specs)
            package = pkg
        else:
            template = SPACED_TEMPLATE if ("-" in mpn and rng.random() < 0.12) else rng.choice(SHOP_TEMPLATES)
            title = template.format(**fill)
            listing_mpn = None
            roll = rng.random()
            manufacturer = (
                None
                if roll < 0.5 or not mfr
                else ("Generic" if roll < 0.6 else rng.choice(MFR_ALIASES.get(mfr, [mfr])))
            )
            listing_gtin = None
            keys = list(specs)
            rng.shuffle(keys)
            spec_subset = {k: specs[k] for k in keys[: rng.randint(0, len(keys))]}
            package = pkg if rng.random() < 0.3 else None
        out.append(
            {
                "id": str(uuid.UUID(int=rng.getrandbits(128))),
                "truth": truth,
                "title": title,
                "mpn": listing_mpn,
                "mpn_trusted": listing_mpn is not None,
                "manufacturer": manufacturer,
                "gtin": listing_gtin,
                "package": package,
                "specs": spec_subset,
            }
        )
    return out


def main() -> None:
    rng = random.Random(20261011)
    counts = [4] * len(PARTS)  # 50 × 4 = 200
    listings: list[dict[str, object]] = []
    for part, n in zip(PARTS, counts, strict=True):
        listings.extend(_variants(rng, part, n))
    rng.shuffle(listings)
    assert len(listings) == 200
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"note": __doc__.strip().splitlines()[0], "listings": listings}, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(listings)} listings, {len(PARTS)} parts")


if __name__ == "__main__":
    main()
