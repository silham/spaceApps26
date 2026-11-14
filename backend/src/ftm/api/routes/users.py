"""Self-service accounts. No account directory or implicit administrator privileges."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ftm.api.auth import (
    COOKIE,
    SessionDep,
    UserDep,
    issue_session,
    password_hash,
    password_matches,
    token_hash,
)
from ftm.config import get_settings
from ftm.contracts.models import LoginRequest, PasswordChange, ProfileUpdate, RegisterRequest, User
from ftm.db.models import UserRow, UserSessionRow
from ftm.provenance import new_id

router = APIRouter(prefix="/auth", tags=["accounts"])
# Equal KDF work for an unknown username, without retaining an actual password.
DUMMY_HASH = "scrypt$" + "00" * 16 + "$" + "00" * 64


@router.post("/register", response_model=User, status_code=201)
def register(req: RegisterRequest, session: SessionDep, response: Response, request: Request) -> User:
    row = UserRow(
        id=new_id("usr"),
        username=req.username,
        display_name=req.display_name,
        password_hash=password_hash(req.password),
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "That username is already taken") from None
    issue_session(session, row, response, request)
    return User.model_validate(row)


@router.post("/login", response_model=User)
def login(req: LoginRequest, session: SessionDep, response: Response, request: Request) -> User:
    row = session.scalar(select(UserRow).where(UserRow.username == req.username).with_for_update())
    valid = password_matches(req.password, row.password_hash if row else DUMMY_HASH)
    now = datetime.now(UTC)
    if row and row.locked_until and row.locked_until > now:
        raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
    if row is None or not valid:
        if row:
            row.failed_logins = (0 if row.locked_until else row.failed_logins) + 1
            row.locked_until = now + timedelta(minutes=15) if row.failed_logins >= 5 else None
            session.commit()
        raise HTTPException(401, "Invalid username or password")
    row.failed_logins = 0
    row.locked_until = None
    issue_session(session, row, response, request)
    return User.model_validate(row)


@router.get("/me", response_model=User)
def me(user: UserDep, response: Response) -> User:
    response.headers["Cache-Control"] = "no-store"
    return User.model_validate(user)


@router.put("/me", response_model=User)
def update_me(req: ProfileUpdate, user: UserDep, session: SessionDep) -> User:
    user.display_name = req.display_name
    session.commit()
    return User.model_validate(user)


@router.put("/password", status_code=204)
def change_password(
    req: PasswordChange, user: UserDep, session: SessionDep, response: Response, request: Request
) -> None:
    if not password_matches(req.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = password_hash(req.new_password)
    session.execute(delete(UserSessionRow).where(UserSessionRow.user_id == user.id))
    issue_session(session, user, response, request)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: SessionDep) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        session.execute(delete(UserSessionRow).where(UserSessionRow.token_hash == token_hash(token)))
        session.commit()
    response.delete_cookie(COOKIE, path="/", secure=get_settings().session_cookie_secure, httponly=True, samesite="lax")
