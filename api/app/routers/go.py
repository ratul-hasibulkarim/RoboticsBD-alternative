"""Click-out redirect: logs the click (anonymised) and sends the user to the source page."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from api.app import repository as repo
from api.app.deps import GeoDep, SessionDep, SettingsDep
from api.app.security import session_hash

router = APIRouter(tags=["go"])


def apply_affiliate(template: str | None, url: str) -> str:
    if not template:
        return url
    from urllib.parse import quote

    return template.format(url=quote(url, safe=""))


@router.get("/go/{listing_id}", include_in_schema=False)
async def go(
    listing_id: uuid.UUID, request: Request, s: SessionDep, settings: SettingsDep, geo: GeoDep
) -> RedirectResponse:
    found = await repo.listing_with_source(s, listing_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "offer not found")
    listing, source = found
    if not listing.url.startswith(("https://", "http://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad target")
    await repo.record_click(s, listing_id, geo.country, session_hash(settings.secret_key.get_secret_value(), request))
    resp = RedirectResponse(apply_affiliate(source.affiliate_template, listing.url), status_code=302)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "origin"
    return resp
