"""Admin console API (bearer token; every route noindex). Merge/split/review are fully audited."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select, update

from api.app.deps import AdminDep, RedisDep, SessionDep
from api.app.schemas import (
    Accepted,
    ComponentPatch,
    CrawlStatusUpdate,
    GuidePublish,
    MergeRequest,
    ReviewItemOut,
    ReviewResolve,
    SourceOut,
    SplitRequest,
    TakedownDecision,
)
from common.models import Component, Guide, Listing, ReviewItem, Source, TakedownRequest
from common.timeutil import utcnow
from resolver.merge_audit import MergeRefusedError, merge_components, resolve_review_item, split_component

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _noindex(response: Response) -> None:
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


@router.get("/review", response_model=list[ReviewItemOut])
async def review_queue(
    s: SessionDep,
    actor: AdminDep,
    response: Response,
    kind: str | None = None,
    status_: Annotated[str, Query(alias="status")] = "open",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ReviewItemOut]:
    _noindex(response)
    q = select(ReviewItem).where(ReviewItem.status == status_).order_by(ReviewItem.created_at).limit(limit)
    if kind:
        q = q.where(ReviewItem.kind == kind)
    return [ReviewItemOut.model_validate(r, from_attributes=True) for r in (await s.execute(q)).scalars()]


@router.post("/review/{item_id}/resolve", response_model=Accepted)
async def resolve_item(item_id: int, body: ReviewResolve, s: SessionDep, actor: AdminDep) -> Accepted:
    item = await s.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if item.kind == "match":
        try:
            await resolve_review_item(s, item_id, component_id=body.component_id, actor=actor)
        except MergeRefusedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    else:
        item.status, item.resolved_at, item.resolved_by = "resolved", utcnow(), actor
    return Accepted(id=str(item_id))


@router.post("/components/merge", response_model=Accepted)
async def merge(body: MergeRequest, s: SessionDep, actor: AdminDep) -> Accepted:
    try:
        moved = await merge_components(s, body.keep, body.drop, actor=actor, force=body.force)
    except MergeRefusedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    from crawler.tasks import index_component

    index_component.delay(str(body.keep))
    index_component.delay(str(body.drop))
    return Accepted(id=f"moved:{moved}")


@router.post("/components/{component_id}/split", response_model=Accepted)
async def split(component_id: uuid.UUID, body: SplitRequest, s: SessionDep, actor: AdminDep) -> Accepted:
    try:
        new_id = await split_component(
            s, component_id, body.listing_ids, new_mpn=body.new_mpn, new_manufacturer=body.new_manufacturer, actor=actor
        )
    except MergeRefusedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    from crawler.tasks import index_component

    index_component.delay(str(component_id))
    index_component.delay(str(new_id))
    return Accepted(id=str(new_id))


@router.patch("/components/{component_id}", response_model=Accepted)
async def patch_component(component_id: uuid.UUID, body: ComponentPatch, s: SessionDep, actor: AdminDep) -> Accepted:
    values = body.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nothing to update")
    values["updated_at"] = utcnow()
    res = await s.execute(update(Component).where(Component.id == component_id).values(**values))
    if not res.rowcount:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "component not found")
    return Accepted(id=str(component_id))


@router.get("/sources", response_model=list[SourceOut])
async def sources(s: SessionDep, actor: AdminDep) -> list[SourceOut]:
    rows = (await s.execute(select(Source).order_by(Source.name))).scalars()
    return [SourceOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/sources/{name}/crawl-status", response_model=Accepted)
async def set_crawl_status(
    name: str, body: CrawlStatusUpdate, s: SessionDep, redis: RedisDep, actor: AdminDep
) -> Accepted:
    src = (await s.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
    if src is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    src.crawl_status, src.crawl_status_reason, src.crawl_status_at = body.status, f"{actor}: {body.reason}", utcnow()
    await redis.delete(f"source:crawl_status:{src.id}")
    return Accepted(id=name)


@router.post("/takedowns/{request_id}", response_model=Accepted)
async def decide_takedown(request_id: uuid.UUID, body: TakedownDecision, s: SessionDep, actor: AdminDep) -> Accepted:
    """Accepting blocks every source on that domain at once and hides its listings. The YAML
    registry must also be updated to legal_review.status: blocked (sync would otherwise revert)."""
    req = await s.get(TakedownRequest, request_id)
    if req is None or req.status != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no open request")
    req.status, req.resolved_at = ("accepted" if body.accept else "rejected"), utcnow()
    if body.accept:
        srcs = list((await s.execute(select(Source).where(Source.domain == req.domain))).scalars())
        for src in srcs:
            src.legal_review_status, src.active, src.crawl_status = "blocked", False, "disabled"
            src.crawl_status_reason = f"takedown {request_id} accepted by {actor}"
            await s.execute(update(Listing).where(Listing.source_id == src.id).values(active=False))
    return Accepted(id=str(request_id))


@router.post("/guides/{guide_id}/publish", response_model=Accepted)
async def publish_guide(guide_id: uuid.UUID, body: GuidePublish, s: SessionDep, actor: AdminDep) -> Accepted:
    guide = await s.get(Guide, guide_id)
    if guide is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "guide not found")
    guide.status, guide.reviewed_by, guide.reviewed_at = "published", f"{body.reviewer} ({actor})", utcnow()
    return Accepted(id=str(guide_id))
