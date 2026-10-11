from __future__ import annotations

from decimal import Decimal

import pytest

from crawler.normalizer.country import to_iso2
from crawler.normalizer.currency import from_minor, parse_price, to_minor
from crawler.normalizer.gtin import normalize_gtin
from crawler.normalizer.mpn import (
    guess_mpn,
    manufacturer_key,
    mpn_key,
    mpn_match_key,
    normalize_manufacturer,
    normalize_mpn,
)
from crawler.normalizer.units import canonical_key, normalize_specs, parse_range, spec_overlap


@pytest.mark.parametrize(
    ("raw", "amount", "cur"),
    [
        ("৳ 1,250.00", "1250.00", "BDT"),
        ("Tk 450", "450", "BDT"),
        ("BDT 1,250", "1250", "BDT"),
        ("৳১,২৫০", "1250", "BDT"),
        ("$3.50", "3.50", "USD"),
        ("US$ 0.2585", "0.2585", "USD"),
        ("2,99 €", "2.99", "EUR"),
        ("1.250,00 €", "1250.00", "EUR"),
        ("¥12.30", "12.30", "CNY"),
        ("1 250,50", "1250.50", None),
    ],
)
def test_parse_price(raw: str, amount: str, cur: str | None) -> None:
    got = parse_price(raw)
    assert got is not None
    assert got[0] == Decimal(amount)
    assert got[1] == cur


def test_minor_units() -> None:
    assert to_minor(Decimal("12.345"), "USD") == 1235
    assert to_minor(Decimal("520"), "BDT") == 52000
    assert to_minor(Decimal("100"), "JPY") == 100
    assert from_minor(52000, "BDT") == Decimal("520")


def test_mpn_forms() -> None:
    assert normalize_mpn(" lm2596s–adj ") == "LM2596S-ADJ"
    assert mpn_key("LM2596S-ADJ") == "lm2596sadj"
    assert mpn_key("ESP32 WROOM 32") == mpn_key("esp32-wroom-32")
    # packaging suffixes are stripped for matching only
    assert mpn_match_key("296-1411-5-ND") == mpn_key("296-1411-5")
    assert mpn_match_key("LM358DR/TR") == mpn_key("LM358DR")
    assert mpn_match_key("NE555P") == "ne555p"
    assert normalize_mpn("LM358DR-TR") == "LM358DR-TR"  # stored form keeps it


@pytest.mark.parametrize(
    ("title", "mpn"),
    [
        ("LM2596S-ADJ DC-DC Step Down Buck Converter Module", "LM2596S-ADJ"),
        ("ESP32-WROOM-32 WiFi Bluetooth Module", "ESP32-WROOM-32"),
        ("DHT22 / AM2302 Temperature and Humidity Sensor", "DHT22"),
        ("10K Ohm 1/4W Resistor (100 pcs)", None),
        ("5V 2A USB Type-C Charger", None),
        ("Arduino Uno R3 compatible board ATmega328P", "ATMEGA328P"),
    ],
)
def test_guess_mpn(title: str, mpn: str | None) -> None:
    assert guess_mpn(title) == mpn


def test_manufacturer_aliases() -> None:
    assert normalize_manufacturer("TI") == "Texas Instruments"
    assert normalize_manufacturer("Texas Instruments Inc.") == "Texas Instruments"
    assert normalize_manufacturer("Microchip Technology Inc") == "Microchip"
    assert normalize_manufacturer("Atmel") == "Microchip"
    assert normalize_manufacturer("Generic") == ""
    assert normalize_manufacturer("Some New Vendor Ltd.") == "Some New Vendor"
    assert manufacturer_key("STMicro") == manufacturer_key("ST Microelectronics")


def test_units_and_ranges() -> None:
    assert parse_range("3.0V ~ 3.6V") == {"min": 3.0, "max": 3.6, "unit": "V"}
    assert parse_range("-40 to 85 °C") == {"min": -40.0, "max": 85.0, "unit": "°C"}
    assert parse_range("4.7µF") == {"value": 4.7e-6, "unit": "F"}
    assert parse_range("10kΩ") == {"value": 10000.0, "unit": "Ω"}
    assert parse_range("1/4W") == {"value": 0.25, "unit": "W"}
    assert parse_range("SOT-23") is None
    assert canonical_key("Operating Voltage:") == "supply_voltage"
    assert canonical_key("Voltage - Supply") == "voltage_supply"


def test_spec_overlap() -> None:
    _, a = normalize_specs({"Operating Voltage": "3.0V ~ 3.6V", "Flash": "4MB", "Interface": "UART"})
    _, b = normalize_specs({"Supply voltage": "3.0-3.6V", "Flash": "4 MB", "Interface": "uart"})
    _, c = normalize_specs({"Supply voltage": "5V", "Flash": "16MB"})
    assert spec_overlap(a, b) == 1.0
    assert spec_overlap(a, c) == 0.0
    assert spec_overlap(a, {}) == 1.0


def test_gtin() -> None:
    assert normalize_gtin("0751492000015") == "00751492000015"
    assert normalize_gtin("0751492000017") is None
    assert normalize_gtin("abc") is None
    assert normalize_gtin("00000000") is None


def test_country() -> None:
    assert to_iso2("Bangladesh") == "BD"
    assert to_iso2("USA") == "US"
    assert to_iso2("de") == "DE"
    assert to_iso2("Atlantis") is None
