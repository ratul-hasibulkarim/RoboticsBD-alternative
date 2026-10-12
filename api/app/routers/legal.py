"""Opt-out / takedown requests, data-error reports, and 'notify me when indexed'."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.app import repository as repo
from api.app.deps import SessionDep
from api.app.schemas import Accepted, NotifyCreate, OptOutCreate, ReportCreate
from common.models import DataReport, ReviewItem, TakedownRequest

router = APIRouter(prefix="/v1", tags=["legal"])


@router.post("/legal/opt-out", response_model=Accepted, status_code=202)
async def opt_out(body: OptOutCreate, s: SessionDep) -> Accepted:
    req = TakedownRequest(domain=body.domain.lower(), contact_email=body.contact_email, reason=body.reason)
    s.add(req)
    await s.flush()
    s.add(
        ReviewItem(
            kind="takedown",
            ref_id=str(req.id),
            reason=f"opt-out request for {req.domain}",
            payload={"domain": req.domain},
        )
    )
    return Accepted(id=str(req.id))


@router.post("/reports", response_model=Accepted, status_code=202)
async def report(body: ReportCreate, s: SessionDep) -> Accepted:
    if body.component_slug is None and body.listing_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "component_slug or listing_id required")
    comp_id = None
    if body.component_slug:
        comp = await repo.component_by_slug(s, body.component_slug)
        if comp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "component not found")
        comp_id = comp.id
    rep = DataReport(component_id=comp_id, listing_id=body.listing_id, field=body.field, message=body.message)
    s.add(rep)
    await s.flush()
    return Accepted(id=str(rep.id))


@router.post("/notify-when-indexed", response_model=Accepted, status_code=202)
async def notify_when_indexed(body: NotifyCreate, s: SessionDep) -> Accepted:
    s.add(
        ReviewItem(
            kind="submission",
            ref_id=f"notify:{body.q.lower()}:{body.email.lower()}",
            reason="user wants to be notified when this part is indexed",
            payload={"q": body.q, "email": body.email},
        )
    )
    try:
        await s.flush()
    except Exception:  # duplicate open request → idempotent
        await s.rollback()
    return Accepted()
