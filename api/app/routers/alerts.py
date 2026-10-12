"""Price alerts with passwordless e-mail login (magic link → session token)."""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from email.message import EmailMessage
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from api.app import repository as repo
from api.app.deps import SessionDep, SettingsDep
from api.app.presenters import decimal_target_to_minor
from api.app.schemas import Accepted, AlertCreate, AlertOut, MagicLinkRequest, SessionOut, SessionRequest
from api.app.security import MAGIC_LINK_TTL_S, SESSION_TTL_S, sign_token, verify_token
from common.models import Component, PriceAlert, User
from common.settings import Settings
from crawler.normalizer.currency import from_minor

router = APIRouter(prefix="/v1", tags=["alerts"])
MAX_ALERTS_FREE = 10


def _send_login_mail(settings: Settings, email: str, link: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_sender
    msg["To"] = email
    msg["Subject"] = "Your VoltFind sign-in link"
    msg.set_content(
        f"Sign in to manage your price alerts (valid 30 minutes):\n\n{link}\n\nIf you didn't ask for this, ignore it."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_username:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)


@router.post("/alerts/request-link", response_model=Accepted, status_code=202)
async def request_link(body: MagicLinkRequest, settings: SettingsDep) -> Accepted:
    token = sign_token(
        settings.secret_key.get_secret_value(), {"purpose": "login", "email": body.email.lower()}, MAGIC_LINK_TTL_S
    )
    link = f"{settings.public_site_url}/alerts?token={token}"
    try:
        await asyncio.to_thread(_send_login_mail, settings, body.email, link)
    except OSError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "mail service unavailable") from exc
    return Accepted()  # same response whether or not the address exists (no account enumeration)


@router.post("/alerts/session", response_model=SessionOut)
async def create_session(body: SessionRequest, s: SessionDep, settings: SettingsDep) -> SessionOut:
    claims = verify_token(settings.secret_key.get_secret_value(), body.token, purpose="login")
    email = str(claims["email"])
    uid = (
        await s.execute(
            insert(User)
            .values(email=email)
            .on_conflict_do_update(index_elements=["email"], set_={"email": email})
            .returning(User.id)
        )
    ).scalar_one()
    token = sign_token(
        settings.secret_key.get_secret_value(), {"purpose": "session", "uid": str(uid), "email": email}, SESSION_TTL_S
    )
    return SessionOut(session_token=token, email=email)


def _user_id(settings: Settings, authorization: str | None) -> uuid.UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    claims = verify_token(settings.secret_key.get_secret_value(), authorization[7:], purpose="session")
    return uuid.UUID(str(claims["uid"]))


AuthHeader = Annotated[str | None, Header()]


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(s: SessionDep, settings: SettingsDep, authorization: AuthHeader = None) -> list[AlertOut]:
    uid = _user_id(settings, authorization)
    rows = (
        await s.execute(
            select(PriceAlert, Component.slug, Component.title)
            .join(Component, Component.id == PriceAlert.component_id)
            .where(PriceAlert.user_id == uid)
            .order_by(PriceAlert.created_at.desc())
        )
    ).all()
    return [
        AlertOut(
            id=a.id,
            component_slug=slug,
            component_title=title,
            target=from_minor(a.target_minor, a.currency),
            currency=a.currency,
            quantity=a.quantity,
            ship_to=a.ship_to,
            active=a.active,
            armed=a.armed,
            last_fired_at=a.last_fired_at,
        )
        for a, slug, title in rows
    ]


@router.post("/alerts", response_model=Accepted, status_code=201)
async def create_alert(
    body: AlertCreate, s: SessionDep, settings: SettingsDep, authorization: AuthHeader = None
) -> Accepted:
    uid = _user_id(settings, authorization)
    comp = await repo.component_by_slug(s, body.component_slug)
    if comp is None or comp.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "component not found")
    count = (
        await s.execute(
            select(func.count()).select_from(PriceAlert).where(PriceAlert.user_id == uid, PriceAlert.active)
        )
    ).scalar_one()
    if count >= MAX_ALERTS_FREE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"limit of {MAX_ALERTS_FREE} active alerts reached")
    alert = PriceAlert(
        user_id=uid,
        component_id=comp.id,
        target_minor=decimal_target_to_minor(body.target, body.currency),
        currency=body.currency,
        quantity=body.quantity,
        ship_to=body.ship_to.upper(),
    )
    s.add(alert)
    await s.flush()
    return Accepted(id=str(alert.id))


@router.delete("/alerts/{alert_id}", response_model=Accepted)
async def delete_alert(
    alert_id: uuid.UUID, s: SessionDep, settings: SettingsDep, authorization: AuthHeader = None
) -> Accepted:
    uid = _user_id(settings, authorization)
    res = await s.execute(delete(PriceAlert).where(PriceAlert.id == alert_id, PriceAlert.user_id == uid))
    if not res.rowcount:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    return Accepted()


@router.delete("/account", response_model=Accepted)
async def delete_account(s: SessionDep, settings: SettingsDep, authorization: AuthHeader = None) -> Accepted:
    """LEGAL §5: deletes the user and (cascade) every alert."""
    uid = _user_id(settings, authorization)
    await s.execute(delete(User).where(User.id == uid))
    return Accepted()
