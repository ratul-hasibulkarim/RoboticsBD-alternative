"""Resolver orchestration: features → candidates → cascade → attach / create / review, with audit."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from crawler.normalizer.mpn import (
    guess_mpn,
    mpn_match_key,
    normalize_mpn,
    strip_packaging,
    title_mpn_keys,
)
from crawler.normalizer.units import normalize_specs
from resolver.embedder import Embedder, embedding_text
from resolver.matcher import (
    ATTACH_THRESHOLD,
    Action,
    Candidate,
    Decision,
    ListingFeatures,
    match,
    refine_untrusted_mpn,
)


@dataclass(frozen=True)
class ResolvableListing:
    id: uuid.UUID
    title: str
    mpn: str | None
    mpn_trusted: bool
    manufacturer: str | None
    gtin: str | None
    package: str | None
    specs: dict[str, str] = field(default_factory=dict)
    category_hint: str | None = None
    datasheet_url: str | None = None
    snippet: str | None = None


@dataclass(frozen=True)
class NewComponent:
    mpn: str
    manufacturer: str | None
    gtin: str | None
    package: str | None
    title: str
    category_hint: str | None
    specs: dict[str, str]
    specs_norm: dict[str, Any]
    embedding: list[float]
    datasheet_url: str | None
    short_desc: str | None


class ComponentIndex(Protocol):
    async def candidates(self, f: ListingFeatures) -> list[Candidate]: ...
    async def create(self, c: NewComponent) -> uuid.UUID: ...
    async def attach(
        self, listing_id: uuid.UUID, component_id: uuid.UUID, confidence: float, method: str
    ) -> None: ...
    async def review(self, listing_id: uuid.UUID, decision: Decision, payload: dict[str, Any]) -> None: ...
    async def audit(
        self,
        action: str,
        *,
        listing_id: uuid.UUID | None,
        from_component: uuid.UUID | None,
        to_component: uuid.UUID | None,
        confidence: float | None,
        method: str | None,
        actor: str,
        details: dict[str, Any],
    ) -> None: ...


def features_for(item: ResolvableListing, embedder: Embedder) -> tuple[ListingFeatures, dict[str, str], dict[str, Any]]:
    human, machine = normalize_specs(item.specs)
    mpn = item.mpn or guess_mpn(item.title)  # same guess the extraction pipeline makes
    emb = embedder.embed([embedding_text(item.manufacturer, mpn, item.title, human)])[0]
    f = ListingFeatures(
        mpn=normalize_mpn(mpn) if mpn else None,
        mpn_trusted=item.mpn_trusted,
        manufacturer=item.manufacturer,
        gtin=item.gtin,
        package=item.package,
        title=item.title,
        specs_norm=machine,
        embedding=emb,
        title_keys=frozenset() if item.mpn_trusted else frozenset(title_mpn_keys(item.title)),
    )
    return f, human, machine


class Resolver:
    ACTOR = "resolver"

    def __init__(self, index: ComponentIndex, embedder: Embedder) -> None:
        self.index = index
        self.embedder = embedder

    async def resolve(self, item: ResolvableListing, *, allow_untrusted_create: bool = True) -> Decision:
        """Resolve one listing. Callers pass allow_untrusted_create=False on the first attempt
        and True on the deferred retry (crawler/tasks.py schedules it 24 h later)."""
        f, human, machine = features_for(item, self.embedder)
        candidates = await self.index.candidates(f)
        f = refine_untrusted_mpn(f, candidates)
        d = match(f, candidates, allow_untrusted_create=allow_untrusted_create)
        if d.action is Action.DEFER:
            return d

        if d.action is Action.ATTACH and d.component_id is not None and d.confidence >= ATTACH_THRESHOLD:
            await self.index.attach(item.id, d.component_id, d.confidence, d.method)
            await self.index.audit(
                "attach",
                listing_id=item.id,
                from_component=None,
                to_component=d.component_id,
                confidence=d.confidence,
                method=d.method,
                actor=self.ACTOR,
                details={"reason": d.reason, "mpn": f.mpn, "manufacturer": f.manufacturer},
            )
            return d

        if d.action is Action.CREATE and f.mpn:
            assert f.embedding is not None
            cid = await self.index.create(
                NewComponent(
                    # canonical part number: packaging/ordering suffixes removed (-TR, /CT, ...)
                    mpn=strip_packaging(f.mpn),
                    manufacturer=item.manufacturer,
                    gtin=item.gtin,
                    package=item.package,
                    title=item.title,
                    category_hint=item.category_hint,
                    specs=human,
                    specs_norm=machine,
                    embedding=f.embedding,
                    datasheet_url=item.datasheet_url,
                    short_desc=item.snippet,
                )
            )
            await self.index.audit(
                "create",
                listing_id=item.id,
                from_component=None,
                to_component=cid,
                confidence=1.0,
                method="new",
                actor=self.ACTOR,
                details={"reason": d.reason, "mpn": f.mpn, "match_key": mpn_match_key(f.mpn)},
            )
            await self.index.attach(item.id, cid, 1.0, "new")
            await self.index.audit(
                "attach",
                listing_id=item.id,
                from_component=None,
                to_component=cid,
                confidence=1.0,
                method="new",
                actor=self.ACTOR,
                details={"reason": "first listing of new component"},
            )
            return Decision(Action.CREATE, cid, 1.0, "new", d.reason)

        await self.index.review(
            item.id,
            d,
            {
                "title": item.title,
                "mpn": f.mpn,
                "manufacturer": item.manufacturer,
                "suggested_component": str(d.component_id) if d.component_id else None,
                "confidence": d.confidence,
                "method": d.method,
                "reason": d.reason,
            },
        )
        return Decision(Action.REVIEW, d.component_id, d.confidence, d.method, d.reason)
