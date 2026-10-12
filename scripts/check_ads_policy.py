#!/usr/bin/env python3
"""CI gate W7: fail if any page template violates ads/placement_policy.yaml (§11.1).

Checks
  1. The runtime policy in web/components/ads/AdSlot.tsx mirrors the YAML (templates, heights, cap).
  2. Every <AdSlot> uses an allowed placement on a template that placement allows, and the
     template attribute matches the route the file renders.
  3. ≤ max_slots_per_page AdSlots per page file (plus shared components it renders).
  4. Templates in no_ads_templates contain no AdSlot.
  5. Component pages: the ad comes after the offer table and specs (never above the fold).
  6. No ad code outside AdSlot.tsx (no auto ads, interstitials, anchors, vignettes, popups, video).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
POLICY_FILE = ROOT / "ads" / "placement_policy.yaml"
ADSLOT = WEB / "components" / "ads" / "AdSlot.tsx"

# route file (relative to web/app) → template name used in the policy
ROUTE_TEMPLATES: dict[str, str] = {
    "page.tsx": "home",
    "search/page.tsx": "search",
    "category/page.tsx": "category",
    "category/[category]/page.tsx": "category",
    "bangladesh/page.tsx": "category",
    "bangladesh/[category]/page.tsx": "category",
    "manufacturer/page.tsx": "manufacturer",
    "manufacturer/[mfr]/page.tsx": "manufacturer",
    "component/[slug]/page.tsx": "component",
    "component/[slug]/prices/page.tsx": "prices",
    "component/[slug]/datasheet/page.tsx": "component",
    "component/[slug]/use-cases/page.tsx": "use_case",
    "component/[slug]/alternatives/page.tsx": "component",
    "compare/page.tsx": "compare_empty",
    "alerts/page.tsx": "alerts",
    "admin/page.tsx": "admin",
    "legal/page.tsx": "legal",
    "legal/opt-out/page.tsx": "opt_out",
    "bot/page.tsx": "bot",
    "not-found.tsx": "not_found",
}
# Shared components that render AdSlot, and the template prop they pass through.
SHARED_WITH_ADS = {"BrowsePage": "BrowseGrid"}

FORBIDDEN_CODE = [
    (r"enable_page_level_ads|data-auto-ad|google_ad_frequency_hint", "auto ads are disabled"),
    (r"vignette|interstitial", "interstitials are forbidden"),
    (r"data-anchor-status|anchor_ads|overlays:\s*\{\s*bottom", "anchor ads are forbidden"),
    (r"window\.open\(|popup", "popups are forbidden"),
    (r"<video[^>]*data-ad|imasdk|ima3\.js", "video ads are forbidden"),
]
ADSLOT_RE = re.compile(r"<AdSlot\b([^>]*)/>", re.S)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def ts_policy(src: str) -> dict[str, object]:
    out: dict[str, object] = {}
    m = re.search(r"maxSlotsPerPage:\s*(\d+)", src)
    out["max"] = int(m.group(1)) if m else None
    allowed = {}
    for name, templates, height in re.findall(r"(\w+):\s*\{\s*templates:\s*\[([^\]]*)\],\s*minHeight:\s*(\d+)", src):
        allowed[name] = (sorted(re.findall(r'"(\w+)"', templates)), int(height))
    out["allowed"] = allowed
    return out


def main() -> int:
    policy = yaml.safe_load(POLICY_FILE.read_text())
    errors: list[str] = []
    allowed = policy["allowed"]
    max_slots = int(policy["max_slots_per_page"])
    no_ads = set(policy["no_ads_templates"])

    # 1. runtime mirror
    tsp = ts_policy(ADSLOT.read_text())
    if tsp["max"] != max_slots:
        errors.append(f"AdSlot.tsx maxSlotsPerPage={tsp['max']} but policy says {max_slots}")
    ts_allowed = tsp["allowed"]
    assert isinstance(ts_allowed, dict)
    if set(ts_allowed) != set(allowed):
        errors.append(f"AdSlot.tsx placements {sorted(ts_allowed)} != policy {sorted(allowed)}")
    for name, rule in allowed.items():
        if name in ts_allowed:
            templates, height = ts_allowed[name]
            if templates != sorted(rule["templates"]):
                errors.append(f"{name}: templates differ (tsx {templates} vs yaml {sorted(rule['templates'])})")
            if height != rule["min_height_px"]:
                errors.append(f"{name}: min height differs (tsx {height} vs yaml {rule['min_height_px']})")
    if policy.get("auto_ads") is not False:
        errors.append("auto_ads must be false")

    # 6. forbidden ad code anywhere except AdSlot.tsx
    for f in list(WEB.glob("app/**/*.ts*")) + list(WEB.glob("components/**/*.ts*")) + list(WEB.glob("lib/**/*.ts")):
        src = f.read_text()
        if f != ADSLOT and "adsbygoogle" in src:
            errors.append(f"{f.relative_to(ROOT)}: ad code outside AdSlot.tsx")
        for pat, why in FORBIDDEN_CODE:
            if re.search(pat, src, re.I):
                errors.append(f"{f.relative_to(ROOT)}: {why} ({pat})")

    # 2–5. templates
    app = WEB / "app"
    seen_routes = set()
    for page in sorted(app.rglob("*.tsx")):
        rel = str(page.relative_to(app))
        if not (rel.endswith("page.tsx") or rel == "not-found.tsx"):
            continue
        seen_routes.add(rel)
        template = ROUTE_TEMPLATES.get(rel)
        if template is None:
            errors.append(f"app/{rel}: route not mapped to a template in check_ads_policy.py")
            continue
        src = page.read_text()
        slots = [dict(ATTR_RE.findall(m.group(1))) for m in ADSLOT_RE.finditer(src)]
        for shared, comp in SHARED_WITH_ADS.items():
            if f"<{comp}" in src:
                shared_src = (WEB / "components" / f"{shared}.tsx").read_text()
                n_shared = len(ADSLOT_RE.findall(shared_src))
                tm = re.search(rf'<{comp}[^>]*template="(\w+)"', src, re.S)
                slots += [{"placement": "in_feed_native", "template": tm.group(1) if tm else "?"}] * n_shared
        if template in no_ads and slots:
            errors.append(f"app/{rel}: template '{template}' must not carry ads")
        if len(slots) > max_slots:
            errors.append(f"app/{rel}: {len(slots)} ad slots > {max_slots}")
        for s in slots:
            placement, tmpl = s.get("placement", "?"), s.get("template", "?")
            if placement not in allowed:
                errors.append(f"app/{rel}: placement '{placement}' is not allowed")
                continue
            if tmpl not in allowed[placement]["templates"]:
                errors.append(f"app/{rel}: '{placement}' not allowed on template '{tmpl}'")
            if tmpl != template and template not in no_ads:
                errors.append(f"app/{rel}: AdSlot says template '{tmpl}' but route is '{template}'")
        if template in ("component", "prices") and "<AdSlot" in src:
            ad_pos = src.index("<AdSlot")
            for marker in ('id="offers"', 'id="all-offers"', 'id="specs"', 'id="ds"', 'id="alts"'):
                if marker in src and src.index(marker) > ad_pos:
                    errors.append(f"app/{rel}: ad appears before {marker} (above the fold / before primary content)")
    for missing in sorted(set(ROUTE_TEMPLATES) - seen_routes):
        errors.append(f"check_ads_policy.py maps app/{missing} but the file does not exist")

    for e in errors:
        print("FAIL", e)
    print(f"ads policy: {len(errors)} violation(s) across {len(seen_routes)} templates")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
