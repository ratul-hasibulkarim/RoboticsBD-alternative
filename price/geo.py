"""User location: Cloudflare headers + a static city table (no Nominatim needed for v1.1)."""

from __future__ import annotations

import math
from dataclasses import dataclass

# name (lower) → (country, lat, lon). BD divisional cities + district towns with shops + world hubs.
CITIES: dict[str, tuple[str, float, float]] = {
    "dhaka": ("BD", 23.8103, 90.4125),
    "chattogram": ("BD", 22.3569, 91.7832),
    "chittagong": ("BD", 22.3569, 91.7832),
    "khulna": ("BD", 22.8456, 89.5403),
    "rajshahi": ("BD", 24.3745, 88.6042),
    "sylhet": ("BD", 24.8949, 91.8687),
    "barishal": ("BD", 22.7010, 90.3535),
    "barisal": ("BD", 22.7010, 90.3535),
    "rangpur": ("BD", 25.7439, 89.2752),
    "mymensingh": ("BD", 24.7471, 90.4203),
    "cumilla": ("BD", 23.4607, 91.1809),
    "comilla": ("BD", 23.4607, 91.1809),
    "gazipur": ("BD", 23.9999, 90.4203),
    "narayanganj": ("BD", 23.6238, 90.5000),
    "bogura": ("BD", 24.8466, 89.3776),
    "jessore": ("BD", 23.1664, 89.2081),
    "cox's bazar": ("BD", 21.4272, 92.0058),
    "kolkata": ("IN", 22.5726, 88.3639),
    "delhi": ("IN", 28.6139, 77.2090),
    "new delhi": ("IN", 28.6139, 77.2090),
    "mumbai": ("IN", 19.0760, 72.8777),
    "bengaluru": ("IN", 12.9716, 77.5946),
    "shenzhen": ("CN", 22.5431, 114.0579),
    "hong kong": ("HK", 22.3193, 114.1694),
    "singapore": ("SG", 1.3521, 103.8198),
    "kuala lumpur": ("MY", 3.1390, 101.6869),
    "dubai": ("AE", 25.2048, 55.2708),
    "london": ("GB", 51.5074, -0.1278),
    "berlin": ("DE", 52.5200, 13.4050),
    "new york": ("US", 40.7128, -74.0060),
    "san francisco": ("US", 37.7749, -122.4194),
    "dallas": ("US", 32.7767, -96.7970),
    "toronto": ("CA", 43.6532, -79.3832),
    "sydney": ("AU", -33.8688, 151.2093),
    "tokyo": ("JP", 35.6762, 139.6503),
}
# Country fallback when only the country is known: capital / largest city.
COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "BD": (23.8103, 90.4125), "IN": (28.6139, 77.2090), "CN": (22.5431, 114.0579), "HK": (22.3193, 114.1694),
    "SG": (1.3521, 103.8198), "MY": (3.1390, 101.6869), "AE": (25.2048, 55.2708), "GB": (51.5074, -0.1278),
    "DE": (52.5200, 13.4050), "US": (39.8283, -98.5795), "CA": (43.6532, -79.3832), "AU": (-33.8688, 151.2093),
    "JP": (35.6762, 139.6503), "PK": (24.8607, 67.0011), "NP": (27.7172, 85.3240), "LK": (6.9271, 79.8612),
}


@dataclass(frozen=True)
class UserGeo:
    country: str
    city: str | None = None
    lat: float | None = None
    lon: float | None = None


def resolve_geo(country: str | None, city: str | None = None) -> UserGeo:
    if city:
        hit = CITIES.get(city.strip().lower())
        if hit and (not country or hit[0] == country.upper()):
            return UserGeo(hit[0], city.strip().title(), hit[1], hit[2])
    c = (country or "BD").upper()
    centroid = COUNTRY_CENTROIDS.get(c)
    if centroid:
        return UserGeo(c, None, centroid[0], centroid[1])
    return UserGeo(c, None, None, None)


def geo_from_headers(headers: dict[str, str]) -> UserGeo:
    """Cloudflare sets CF-IPCountry (and, with the managed transform, cf-ipcity)."""
    lower = {k.lower(): v for k, v in headers.items()}
    country = lower.get("cf-ipcountry")
    if country in (None, "", "XX", "T1"):
        country = None
    return resolve_geo(country, lower.get("cf-ipcity"))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
