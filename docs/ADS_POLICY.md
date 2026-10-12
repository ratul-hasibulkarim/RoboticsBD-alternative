# Ads policy

Policy file: `ads/placement_policy.yaml`. Runtime enforcement: `web/components/ads/AdSlot.tsx` (re-exported at `ads/adapter.tsx`).
CI enforcement: `scripts/check_ads_policy.py` (gate W7), tested by `tests/python/test_ads_policy.py`.

* Google **AdSense** (web). AdMob was the wrong product for a website (spec v1.1 row 2).
* At most **3 slots per page**, manual placements only, auto ads off.
* Allowed: in-feed after item 8 (search/category/manufacturer); sidebar on viewports ≥ 1280 px;
  below the full offer table (component/prices); article footer (tutorials/guides).
* Forbidden: interstitials, popups, anchor/sticky-bottom mobile ads, anything above the fold on component pages, video ads.
* Space is reserved before the ad loads (no CLS). The ad request fires only when the slot nears the viewport.
* No ad consent → non-personalised ads (`npa=1`).
* Pages with auto-generated prose carry ads only after human review (`prose_reviewed`).
* Measure revenue per template and session depth. Remove any placement that cuts session depth by more than 5 %.

Other revenue (no AdMob dependence): affiliate templates per source (`sources.affiliate_template`, links marked `sponsored`),
clearly labelled sponsored placements for BD shops, and a Pro tier (out of scope for v1.1: needs a BD payment provider).
