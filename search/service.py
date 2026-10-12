"""Search service (§8.2): query understanding → backend (Typesense, Postgres fallback) → cache.

Zero-result fallback (§8.2 step 6, v1.1): no web-search scraping. The query is queued in
Redis `discovery:queue` for the distributor-API discovery job and an admin review item;
the response carries a helpful message and invites an e-mail alert.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from redis.asyncio import Redis
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from common.models import Component, Image, Listing, PriceCurrent, Query, Source
from common.timeutil import utcnow
from crawler.normalizer.mpn import looks_like_mpn, mpn_key
from resolver.embedder import Embedder
from search.indexer import COLLECTION
from search.query_understanding import ParsedQuery, QueryKind, parse_query
from search.typesense import TypesenseClient

FACETS = ("manufacturer", "category", "package", "in_stock", "ships_to_bd")
MAX_PER_PAGE = 50


@dataclass(frozen=True)
class SearchParams:
    q: str
    page: int = 1
    per_page: int = 24
    category: str | None = None
    manufacturer: str | None = None
    package: str | None = None
    in_stock: bool | None = None
    ships_to_bd: bool | None = None
    sort: str = "relevance"  # relevance | price | popularity
    user_country: str | None = None

    def cache_key(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, default=str)
        return "search:" + hashlib.sha256(raw.lower().encode()).hexdigest()[:32]


@dataclass(frozen=True)
class SearchHit:
    id: str
    slug: str
    mpn: str
    title: str
    manufacturer: str | None
    category: str
    package: str | None
    lowest_price_usd_minor: int | None
    offer_count: int
    in_stock: bool
    ships_to_bd: bool
    image_url: str | None


@dataclass
class SearchResponse:
    query: str
    kind: str
    hits: list[SearchHit]
    found: int
    page: int
    per_page: int
    facets: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    backend: str = "typesense"
    took_ms: float = 0.0
    message: str | None = None
    discovery_queued: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, raw: bytes | str) -> SearchResponse:
        d = json.loads(raw)
        d["hits"] = [SearchHit(**h) for h in d["hits"]]
        d["facets"] = {k: [tuple(x) for x in v] for k, v in d["facets"].items()}
        return cls(**d)


class SearchBackend(Protocol):
    name: str

    async def search(self, p: SearchParams, pq: ParsedQuery, embedding: list[float] | None) -> SearchResponse: ...


def _esc(v: str) -> str:
    return "`" + v.replace("`", "") + "`"


class TypesenseBackend:
    name = "typesense"

    def __init__(self, client: TypesenseClient) -> None:
        self.client = client

    def build_request(self, p: SearchParams, pq: ParsedQuery, embedding: list[float] | None) -> dict[str, Any]:
        filters = []
        if p.category or pq.category:
            filters.append(f"category:={_esc(p.category or pq.category or '')}")
        if p.manufacturer:
            filters.append(f"manufacturer:={_esc(p.manufacturer)}")
        if p.package:
            filters.append(f"package:={_esc(p.package)}")
        if p.in_stock is not None:
            filters.append(f"in_stock:={str(p.in_stock).lower()}")
        if p.ships_to_bd is not None or pq.wants_bd:
            filters.append(f"ships_to_bd:={str(p.ships_to_bd if p.ships_to_bd is not None else True).lower()}")
        if pq.max_price_usd_minor:
            filters.append(f"lowest_price_usd_minor:<={pq.max_price_usd_minor}")

        if p.sort == "price":
            sort_by = "lowest_price_usd_minor:asc,_text_match:desc"
        elif p.sort == "popularity":
            sort_by = "popularity:desc,_text_match:desc"
        elif (p.user_country or "").upper() == "BD":
            sort_by = "_text_match:desc,ships_to_bd:desc,popularity:desc"  # geo boost (§8.2 step 5)
        else:
            sort_by = "_text_match:desc,popularity:desc"

        # Category queries ("10k resistor 0805") filter by category AND rank by their words.
        q = pq.mpn_key if pq.kind is QueryKind.MPN and pq.mpn_key else pq.norm
        req: dict[str, Any] = {
            "collection": COLLECTION,
            "q": q,
            "query_by": "mpn_norm,mpn,title,manufacturer,specs_text",
            "query_by_weights": "5,5,3,1,1",
            "num_typos": "1,1,2,1,0",
            "prefix": "true,true,true,false,false",
            "facet_by": ",".join(FACETS),
            "max_facet_values": 20,
            "sort_by": sort_by,
            "page": p.page,
            "per_page": min(p.per_page, MAX_PER_PAGE),
            "exclude_fields": "embedding,specs_text",
        }
        if filters:
            req["filter_by"] = " && ".join(filters)
        if embedding is not None and pq.kind is QueryKind.NATURAL:
            vec = ",".join(f"{x:.5f}" for x in embedding)
            req["vector_query"] = f"embedding:([{vec}], k:100, alpha:0.3)"  # hybrid: 70 % keyword
        return req

    async def search(self, p: SearchParams, pq: ParsedQuery, embedding: list[float] | None) -> SearchResponse:
        res = (await self.client.multi_search([self.build_request(p, pq, embedding)]))["results"][0]
        if "error" in res:
            raise RuntimeError(res["error"])
        hits = []
        for h in res.get("hits", []):
            d = h["document"]
            hits.append(
                SearchHit(
                    id=d["id"],
                    slug=d["slug"],
                    mpn=d["mpn"],
                    title=d["title"],
                    manufacturer=d.get("manufacturer"),
                    category=d["category"],
                    package=d.get("package"),
                    lowest_price_usd_minor=d.get("lowest_price_usd_minor"),
                    offer_count=d.get("offer_count", 0),
                    in_stock=d.get("in_stock", False),
                    ships_to_bd=d.get("ships_to_bd", False),
                    image_url=d.get("image_url"),
                )
            )
        facets = {
            fc["field_name"]: [(str(c["value"]), int(c["count"])) for c in fc.get("counts", [])]
            for fc in res.get("facet_counts", [])
        }
        return SearchResponse(
            pq.raw, pq.kind.value, hits, int(res.get("found", 0)), p.page, p.per_page, facets, self.name
        )


class PostgresBackend:
    """Fallback when Typesense is unreachable, and the backend used in tests."""

    name = "postgres"

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def search(self, p: SearchParams, pq: ParsedQuery, embedding: list[float] | None) -> SearchResponse:
        stats = (
            select(
                Listing.component_id.label("cid"),
                func.min(PriceCurrent.landed_usd_minor).filter(Listing.in_stock.is_not(False)).label("lowest"),
                func.count(PriceCurrent.listing_id).label("offers"),
                func.coalesce(func.bool_or(Listing.in_stock.is_(True)), False).label("in_stock"),
                func.coalesce(
                    func.bool_or(
                        or_(
                            func.array_position(Listing.ships_to, "BD").is_not(None),
                            func.array_position(Listing.ships_to, "*").is_not(None),
                        )
                    ),
                    False,
                ).label("ships_bd"),
            )
            .join(PriceCurrent, PriceCurrent.listing_id == Listing.id)
            .join(Source, and_(Source.id == Listing.source_id, Source.active.is_(True)))
            .where(Listing.active.is_(True))
            .group_by(Listing.component_id)
            .subquery()
        )
        conds = [Component.status == "active"]
        rank: ColumnElement[Any] = literal(0.0)
        words = [w for w in pq.norm.split() if len(w) >= 2][:6]
        if pq.kind is QueryKind.CATEGORY:
            conds.append(Component.category == pq.category)
        else:
            key = pq.mpn_key or mpn_key(pq.norm)
            text_conds: list[ColumnElement[bool]] = [Component.mpn_norm.like(f"{key}%")] if key else []
            text_conds += (
                [
                    and_(
                        *[
                            or_(
                                Component.title.ilike(f"%{w}%"),
                                Component.manufacturer.ilike(f"%{w}%"),
                                Component.mpn.ilike(f"%{w}%"),
                            )
                            for w in words
                        ]
                    )
                ]
                if words
                else []
            )
            if embedding is not None and pq.kind is QueryKind.NATURAL:
                text_conds.append(Component.embedding.cosine_distance(embedding) < 0.5)
            conds.append(or_(*text_conds) if text_conds else literal(False))
            rank = (
                case((Component.mpn_norm == key, 10.0), else_=0.0)
                + case((Component.mpn_norm.like(f"{key}%"), 5.0), else_=0.0)
                + case((Component.title.ilike(f"%{pq.norm}%"), 1.0), else_=0.0)
            )
        # Each query word found in title/manufacturer/MPN/category counts (keyword relevance) …
        for w in words:
            rank = rank + case(
                (
                    or_(
                        # whole-token match: "10k" must not score on "110K"; "4.7k" matches "4.7kΩ"
                        Component.title.op("~*")(rf"(^|[^0-9A-Za-z]){re.escape(w)}(?![0-9A-Za-z])"),
                        Component.manufacturer.op("~*")(rf"(^|[^0-9A-Za-z]){re.escape(w)}(?![0-9A-Za-z])"),
                        Component.mpn.ilike(f"%{w}%") if looks_like_mpn(w) else literal(False),
                        Component.subcategory.ilike(f"%{w}%"),
                    ),
                    2.0,
                ),
                else_=0.0,
            )
        # … plus semantic similarity as a tie-breaker (hybrid, like the Typesense path).
        if embedding is not None and pq.kind is QueryKind.NATURAL:
            rank = rank + (1.0 - func.coalesce(Component.embedding.cosine_distance(embedding), 1.0))
        if p.category:
            conds.append(Component.category == p.category)
        if p.manufacturer:
            conds.append(Component.manufacturer == p.manufacturer)
        if p.package:
            conds.append(Component.package == p.package)
        if p.in_stock is not None:
            conds.append(func.coalesce(stats.c.in_stock, False) == p.in_stock)
        if p.ships_to_bd is not None or pq.wants_bd:
            conds.append(
                func.coalesce(stats.c.ships_bd, False) == (p.ships_to_bd if p.ships_to_bd is not None else True)
            )
        if pq.max_price_usd_minor:
            conds.append(stats.c.lowest <= pq.max_price_usd_minor)

        base = (
            select(Component, stats.c.lowest, stats.c.offers, stats.c.in_stock, stats.c.ships_bd, Image.source_url)
            .outerjoin(stats, stats.c.cid == Component.id)
            .outerjoin(Image, Image.id == Component.primary_image)
            .where(*conds)
        )
        found = (await self.s.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        order: list[Any]
        if p.sort == "price":
            order = [stats.c.lowest.asc().nulls_last(), Component.popularity.desc()]
        elif p.sort == "popularity":
            order = [Component.popularity.desc()]
        else:
            order = [rank.desc(), Component.popularity.desc(), Component.slug]
        per_page = min(p.per_page, MAX_PER_PAGE)
        rows = (await self.s.execute(base.order_by(*order).limit(per_page).offset((p.page - 1) * per_page))).all()
        hits = [
            SearchHit(
                id=str(c.id),
                slug=c.slug,
                mpn=c.mpn,
                title=c.title,
                manufacturer=c.manufacturer,
                category=c.category,
                package=c.package,
                lowest_price_usd_minor=int(low) if low is not None else None,
                offer_count=int(offers or 0),
                in_stock=bool(stock),
                ships_to_bd=bool(bd),
                image_url=img,
            )
            for c, low, offers, stock, bd, img in rows
        ]
        facets: dict[str, list[tuple[str, int]]] = {}
        sub = base.subquery()
        for fname in ("manufacturer", "category", "package"):
            col = sub.c[fname]
            frows = (
                await self.s.execute(
                    select(col, func.count())
                    .where(col.is_not(None))
                    .group_by(col)
                    .order_by(func.count().desc())
                    .limit(20)
                )
            ).all()
            facets[fname] = [(str(v), int(n)) for v, n in frows]
        return SearchResponse(pq.raw, pq.kind.value, hits, int(found), p.page, per_page, facets, self.name)


class SearchService:
    def __init__(
        self,
        primary: SearchBackend,
        fallback: SearchBackend | None,
        redis: Redis | None,
        embedder: Embedder | None,
        *,
        cache_ttl_s: int = 300,
        session: AsyncSession | None = None,
    ) -> None:
        self.primary, self.fallback, self.redis, self.embedder = primary, fallback, redis, embedder
        self.cache_ttl_s = cache_ttl_s
        self.session = session

    async def search(self, p: SearchParams, *, session_hash: str | None = None) -> SearchResponse:
        t0 = time.perf_counter()
        pq = parse_query(p.q)
        key = p.cache_key()
        if self.redis is not None:
            cached = await self.redis.get(key)
            if cached is not None:
                resp = SearchResponse.from_json(cached)
                resp.took_ms = round((time.perf_counter() - t0) * 1000, 2)
                await self._log(pq, resp, p, session_hash)
                return resp
        emb = self.embedder.embed([pq.norm])[0] if self.embedder is not None and pq.kind is QueryKind.NATURAL else None
        try:
            resp = await self.primary.search(p, pq, emb)
        except Exception:
            if self.fallback is None:
                raise
            resp = await self.fallback.search(p, pq, emb)
        if resp.found == 0 and p.page == 1 and pq.kind is not QueryKind.CATEGORY:
            resp.discovery_queued = await self._queue_discovery(pq)
            resp.message = (
                "We don't have this part yet. We've queued it for lookup at our approved distributor "
                "sources — check back in about an hour, or leave your e-mail to be told when it's in."
            )
        resp.took_ms = round((time.perf_counter() - t0) * 1000, 2)
        if self.redis is not None and resp.found > 0:
            await self.redis.set(key, resp.to_json(), ex=self.cache_ttl_s)
        await self._log(pq, resp, p, session_hash)
        return resp

    async def _queue_discovery(self, pq: ParsedQuery) -> bool:
        if self.redis is None:
            return False
        added = await self.redis.sadd("discovery:seen", pq.norm.lower())
        if added:
            await self.redis.rpush(
                "discovery:queue", json.dumps({"q": pq.norm, "mpn": pq.mpn, "at": utcnow().isoformat()})
            )
        return True

    async def _log(self, pq: ParsedQuery, resp: SearchResponse, p: SearchParams, session_hash: str | None) -> None:
        if self.session is None or p.page != 1:
            return
        self.session.add(
            Query(
                time=utcnow(),
                query_norm=pq.norm.lower()[:200],
                result_count=resp.found,
                user_country=p.user_country,
                session_hash=session_hash,
            )
        )
        await self.session.flush()
