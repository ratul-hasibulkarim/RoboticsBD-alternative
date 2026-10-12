# SEO implementation

* **Rendering**: every public route is SSR/ISR. Component pages pre-build the top 1 000 parts; the rest render on first request.
  `POST /api/revalidate` (secret) refreshes a part as soon as its prices change.
* **Structured data**: Product + AggregateOffer, BreadcrumbList, FAQPage (facts only), HowTo (tutorials),
  Organization, WebSite + SearchAction, Dataset (price history). Validated offline in CI (`npm run validate:schema`).
  FAQ/HowTo rich results are not expected (Google restricts them); the markup is still valid.
* **Canonicals**: every page canonicalises to itself; paginated pages include `?page=`; compare pages
  sort slugs so `a,b` and `b,a` share one canonical. Checked by `site-check.mjs` (W6).
* **Sitemaps**: `/sitemap-index.xml` → `sitemap-components-N.xml` (9 000 parts × 5 sub-pages ≤ 45 000 URLs),
  `sitemap-images-N.xml`, `sitemap-categories.xml`, `sitemap-manufacturers.xml`.
* **robots.txt** blocks `/admin`, `/api/`, `/search`, `/alerts`, `/go/`.
* **Status codes**: unknown → 404, merged → 308 to the survivor, retired → 410 (middleware).
* **Internal linking**: each part links to its category, manufacturer, ≥ 2 alternatives and up to 8 related parts.
* **hreflang**: none until Bengali pages exist (spec v1.1 row 17).
* **Content**: prose on component pages appears only after `prose_reviewed = true`. Guides need a reviewer to publish (DB CHECK).
* **BD intent pages**: `/bangladesh` and `/bangladesh/[category]` list parts that ship to Bangladesh.

See `docs/seo/backlink-plan.md` for off-page work.
