"""Database sessions and explicit ownership checks. Passwords use the standard-library scrypt KDF.

Every farm and run belongs to exactly one account; there are no shared farms. A row without an owner
(e.g. the seeded ks-field-2) is visible to nobody (docs/decisions.md D14)."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ftm.config import get_settings
from ftm.db.models import (
    DecisionRecordRow,
    ProcessingRunRow,
    ResultRow,
    SimulationRunRow,
    SiteRow,
    SoilProfileRow,
    UserRow,
    UserSessionRow,
)
from ftm.db.session import get_session

COOKIE = "ftm_session"
SessionDep = Annotated[Session, Depends(get_session)]


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**17, r=8, p=1, maxmem=256 * 1024**2)
    return f"scrypt${salt}${key.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    _, salt, _ = encoded.split("$")
    return hmac.compare_digest(password_hash(password, salt), encoded)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def protect_mutation(request: Request) -> None:
    # A custom header cannot be submitted by cross-site forms. CORS only permits configured origins.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("X-FTM-Request") != "1":
            raise HTTPException(403, "Missing request protection header")
        origin = request.headers.get("origin")
        if origin and origin not in get_settings().cors_origins:
            raise HTTPException(403, "Origin is not allowed")


def current_user(request: Request, session: SessionDep) -> UserRow | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = session.get(UserSessionRow, token_hash(token))
    if row is None or row.expires_at <= datetime.now(UTC):
        return None
    return session.get(UserRow, row.user_id)


OptionalUser = Annotated[UserRow | None, Depends(current_user)]


def require_user(user: OptionalUser) -> UserRow:
    if user is None:
        raise HTTPException(401, "Sign in to continue")
    return user


UserDep = Annotated[UserRow, Depends(require_user)]


def issue_session(session: Session, user: UserRow, response: Response, request: Request) -> None:
    old = request.cookies.get(COOKIE)
    if old:
        session.execute(delete(UserSessionRow).where(UserSessionRow.token_hash == token_hash(old)))
    session.execute(delete(UserSessionRow).where(UserSessionRow.expires_at <= datetime.now(UTC)))
    token = secrets.token_urlsafe(32)
    seconds = get_settings().session_days * 86400
    session.add(
        UserSessionRow(
            token_hash=token_hash(token), user_id=user.id, expires_at=datetime.now(UTC) + timedelta(seconds=seconds)
        )
    )
    session.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=seconds,
        httponly=True,
        secure=get_settings().session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def visible_sites(user: UserRow) -> ColumnElement[bool]:
    return SiteRow.owner_user_id == user.id


def visible_runs(user: UserRow) -> ColumnElement[bool]:
    return SimulationRunRow.owner_user_id == user.id


def site_access(session: Session, site_id: str, user: UserRow) -> SiteRow:
    row = session.get(SiteRow, site_id)
    if row is None or row.owner_user_id != user.id:
        raise HTTPException(404, "Farm not found")
    return row


def run_access(session: Session, run_id: str, user: UserRow) -> SimulationRunRow:
    row = session.get(SimulationRunRow, run_id)
    if row is None or row.owner_user_id != user.id:
        raise HTTPException(404, "Run not found")
    site_access(session, row.site_id, user)
    return row


def card_access(session: Session, card_id: str, user: UserRow) -> DecisionRecordRow:
    row = session.get(DecisionRecordRow, card_id)
    if row is None:
        raise HTTPException(404, "Decision card not found")
    run_access(session, row.run_id, user)
    return row


def source_ids_for_user(session: Session, user: UserRow) -> set[str]:
    ids: set[str] = set()
    for row in session.scalars(
        select(ProcessingRunRow).join(SiteRow, ProcessingRunRow.site_id == SiteRow.id).where(visible_sites(user))
    ):
        ids.update(row.input_source_ids)
    for soil in session.scalars(
        select(SoilProfileRow).join(SiteRow, SoilProfileRow.site_id == SiteRow.id).where(visible_sites(user))
    ):
        ids.update(soil.params.get("source_ids", []))
    for result in session.scalars(
        select(ResultRow)
        .join(SimulationRunRow, ResultRow.run_id == SimulationRunRow.id)
        .join(SiteRow, SimulationRunRow.site_id == SiteRow.id)
        .where(visible_sites(user), visible_runs(user))
    ):
        ids.update(result.source_ids)
    return ids
