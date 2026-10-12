"""Public component endpoints: detail (the SEO page payload), offers, history, browse, compare, sitemap."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from api.app import repository as repo
from api.app.deps import FxDep, GeoDep, SessionDep
from api.app.presenters import (
    DISPLAY_CURRENCIES,
    build_faq,
    default_currency,
    offers_out,
    price_range,
    ranked_offers,
)
from api.app.schemas import (
    Breadcrumb,
    CategoryOut,
    CompareOut,
    ComponentCard,
    ComponentDetail,
    DatasheetOut,
    FaqItem,
    HistoryPoint,
    ImageOut,
    ManufacturerOut,
    OffersOut,
    PagedComponents,
    SitemapEntry,
    UseCaseOut,
)
from common.models import Component
from common.timeutil import utcnow
from price.ranker import SortMode

router = APIRouter(prefix="/v1", tags=["components"])

CurrencyQ = Annotated[str | None, Query(pattern="^(BDT|USD|EUR)$")]


async def _load(s: SessionDep, slug: str) -> Component:
    comp = await repo.component_by_slug(s, slug)
    if comp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "component not found")
    if comp.status == "merged":
        target = await repo.merged_target_slug(s, comp)
        raise HTTPException(status.HTTP_301_MOVED_PERMANENTLY, detail={"status": "merged", "redirect_to": target})
    if comp.status == "retired":
        raise HTTPException(status.HTTP_410_GONE, detail={"status": "retired", "redirect_to": None})
    return comp


@router.get("/components/{slug}", response_model=ComponentDetail)
async def component_detail(
    slug: str,
    s: SessionDep,
    fx: FxDep,
    geo: GeoDep,
    response: Response,
    currency: CurrencyQ = None,
    track: bool = True,
) -> ComponentDetail:
    comp = await _load(s, slug)
    now = utcnow()
    cur = currency or default_currency(geo)
    ranked = await ranked_offers(
        s, comp, geo, fx, now, mode=SortMode.BEST, quantity=1, local_only=False, in_stock_only=False
    )
    summary = await offers_out(
        s, comp, ranked, geo, fx, now, mode=SortMode.BEST, quantity=1, currency=cur, local_only=False, limit=10
    )
    low, high = price_range(ranked, fx, cur)
    datasheets = await repo.datasheets_for(s, comp.id)
    queries = await repo.top_queries_for(s, comp)
    faq = build_faq(comp, low, len(ranked), bool(datasheets), queries)
    if track:
        await repo.record_view(s, comp.id)
    crumbs = [
        Breadcrumb(name="Home", path="/"),
        Breadcrumb(name=comp.category.replace("-", " ").title(), path=f"/category/{comp.category}"),
    ]
    if comp.manufacturer:
        crumbs.append(
            Breadcrumb(name=comp.manufacturer, path=f"/manufacturer/{repo.manufacturer_slug(comp.manufacturer)}")
        )
    crumbs.append(Breadcrumb(name=comp.mpn, path=f"/component/{comp.slug}"))
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=600"
    return ComponentDetail(
        id=comp.id,
        slug=comp.slug,
        mpn=comp.mpn,
        title=comp.title,
        manufacturer=comp.manufacturer,
        category=comp.category,
        subcategory=comp.subcategory,
        package=comp.package,
        lifecycle=comp.lifecycle,
        short_desc=comp.short_desc,
        prose_md=comp.prose_md if comp.prose_reviewed else None,
        prose_reviewed=comp.prose_reviewed,
        specs={str(k): str(v) for k, v in (comp.specs or {}).items()},
        images=[
            ImageOut(url=i.source_url, width=i.width, height=i.height, attribution=i.attribution, license=i.license)
            for i in await repo.images_for(s, comp.id)
        ],
        datasheets=[DatasheetOut.model_validate(d, from_attributes=True) for d in datasheets],
        use_cases=[UseCaseOut.model_validate(u, from_attributes=True) for u in await repo.use_cases_for(s, comp.id, 6)],
        alternatives=[ComponentCard(**c) for c in await repo.alternatives(s, comp)],
        related=[ComponentCard(**c) for c in await repo.related(s, comp)],
        history=[HistoryPoint(day=d, min_usd_minor=v) for d, v in await repo.history(s, comp.id)],
        offer_summary=summary,
        low_price=low,
        high_price=high,
        offer_count=len(ranked),
        faq=[FaqItem(question=q, answer=a) for q, a in faq],
        breadcrumbs=crumbs,
        updated_at=comp.updated_at,
    )


@router.get("/components/{slug}/offers", response_model=OffersOut)
async def component_offers(
    slug: str,
    s: SessionDep,
    fx: FxDep,
    geo: GeoDep,
    mode: SortMode = SortMode.BEST,
    qty: Annotated[int, Query(ge=1, le=100_000)] = 1,
    local_only: bool = False,
    in_stock_only: bool = False,
    currency: CurrencyQ = None,
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OffersOut:
    comp = await _load(s, slug)
    now = utcnow()
    cur = currency or default_currency(geo)
    ranked = await ranked_offers(
        s, comp, geo, fx, now, mode=mode, quantity=qty, local_only=local_only, in_stock_only=in_stock_only
    )
    page_items = ranked[(page - 1) * per_page : page * per_page]
    out = await offers_out(
        s, comp, page_items, geo, fx, now, mode=mode, quantity=qty, currency=cur, local_only=local_only
    )
    out.total = len(ranked)
    return out


@router.get("/components/{slug}/history", response_model=list[HistoryPoint])
async def component_history(
    slug: str, s: SessionDep, days: Annotated[int, Query(ge=7, le=1825)] = 90
) -> list[HistoryPoint]:
    comp = await _load(s, slug)
    return [HistoryPoint(day=d, min_usd_minor=v) for d, v in await repo.history(s, comp.id, days)]


@router.get("/components/{slug}/use-cases", response_model=list[UseCaseOut])
async def component_use_cases(slug: str, s: SessionDep) -> list[UseCaseOut]:
    comp = await _load(s, slug)
    return [UseCaseOut.model_validate(u, from_attributes=True) for u in await repo.use_cases_for(s, comp.id, 50)]


@router.get("/components/{slug}/datasheets", response_model=list[DatasheetOut])
async def component_datasheets(slug: str, s: SessionDep) -> list[DatasheetOut]:
    comp = await _load(s, slug)
    return [DatasheetOut.model_validate(d, from_attributes=True) for d in await repo.datasheets_for(s, comp.id)]


@router.get("/components/{slug}/alternatives", response_model=list[ComponentCard])
async def component_alternatives(
    slug: str, s: SessionDep, limit: Annotated[int, Query(ge=1, le=24)] = 8
) -> list[ComponentCard]:
    comp = await _load(s, slug)
    return [ComponentCard(**c) for c in await repo.alternatives(s, comp, limit)]


@router.get("/compare", response_model=CompareOut)
async def compare(
    parts: Annotated[str, Query(min_length=3, max_length=400)],
    s: SessionDep,
    fx: FxDep,
    geo: GeoDep,
    currency: CurrencyQ = None,
) -> CompareOut:
    slugs = [p.strip() for p in parts.split(",") if p.strip()][:4]
    if len(slugs) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "compare needs 2–4 parts")
    details = [await component_detail(sl, s, fx, geo, Response(), currency, track=False) for sl in slugs]
    keys: list[str] = []
    for d in details:
        for k in d.specs:
            if k not in keys:
                keys.append(k)
    return CompareOut(components=details, spec_keys=keys)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(s: SessionDep) -> list[CategoryOut]:
    return [CategoryOut(category=c, count=n) for c, n in await repo.categories(s)]


@router.get("/categories/{category}", response_model=PagedComponents)
async def category_page(
    category: str,
    s: SessionDep,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=96)] = 24,
    ships_to_bd: bool = False,
) -> PagedComponents:
    items, total = await repo.components_page(
        s, category=category, page=page, per_page=per_page, ships_to_bd=ships_to_bd
    )
    if total == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown category")
    return PagedComponents(items=[ComponentCard(**i) for i in items], total=total, page=page, per_page=per_page)


@router.get("/manufacturers", response_model=list[ManufacturerOut])
async def list_manufacturers(s: SessionDep) -> list[ManufacturerOut]:
    return [
        ManufacturerOut(manufacturer=m, slug=repo.manufacturer_slug(m), count=n) for m, n in await repo.manufacturers(s)
    ]


@router.get("/manufacturers/{mfr_slug}", response_model=PagedComponents)
async def manufacturer_page(
    mfr_slug: str,
    s: SessionDep,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=96)] = 24,
) -> PagedComponents:
    name = await repo.manufacturer_by_slug(s, mfr_slug)
    if name is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown manufacturer")
    items, total = await repo.components_page(s, manufacturer=name, page=page, per_page=per_page)
    return PagedComponents(items=[ComponentCard(**i) for i in items], total=total, page=page, per_page=per_page)


@router.get("/trending", response_model=list[ComponentCard])
async def trending(s: SessionDep, limit: Annotated[int, Query(ge=1, le=48)] = 12) -> list[ComponentCard]:
    return [ComponentCard(**c) for c in await repo.trending(s, limit)]


@router.get("/sitemap/components", response_model=list[SitemapEntry])
async def sitemap_components(s: SessionDep, page: Annotated[int, Query(ge=1)] = 1) -> list[SitemapEntry]:
    return [SitemapEntry(slug=sl, updated_at=u, image_url=img) for sl, u, img in await repo.sitemap_entries(s, page)]


@router.get("/sitemap/count")
async def sitemap_count(s: SessionDep) -> JSONResponse:
    return JSONResponse(
        {"components": await repo.sitemap_count(s), "per_file": 45_000, "currencies": DISPLAY_CURRENCIES}
    )


@router.get("/sitemap/retired", response_model=list[str])
async def sitemap_retired(s: SessionDep) -> list[str]:
    return await repo.retired_slugs(s)


@router.post("/components/{slug}/view", status_code=204)
async def component_view(slug: str, s: SessionDep) -> Response:
    """Lightweight page-view beacon (feeds crawl priority + trending)."""
    comp = await repo.component_by_slug(s, slug)
    if comp is not None and comp.status == "active":
        await repo.record_view(s, comp.id)
    return Response(status_code=204)
