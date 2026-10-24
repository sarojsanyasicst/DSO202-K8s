"""Guest session bootstrap, instructor login, and the access checks other features' routes use.

State-changing requests pass three checks, in this order:
1. same origin (403): an Origin header, when present, must name this Host, and
   Sec-Fetch-Site must not be cross-site. TLS ends at the gateway, so schemes are not compared;
2. a live session of the right kind (401);
3. the session's CSRF token in the X-CSRF-Token header (403).
Instructor login runs only the same-origin check: it has no session yet.
"""

from datetime import timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import APIKeyCookie

from cloudcart.config import Settings
from cloudcart.db import DbSession
from cloudcart.identity.models import Guest, InstructorSession
from cloudcart.identity.schemas import InstructorCredentials, SessionView
from cloudcart.identity.security import (
    GUEST_SESSION_LIFETIME,
    INSTRUCTOR_SESSION_LIFETIME,
    csrf_token_matches,
    ensure_guest,
    find_live_guest,
    find_live_instructor_session,
    log_in_instructor,
)

GUEST_COOKIE_NAME = "cloudcart_guest"
INSTRUCTOR_COOKIE_NAME = "cloudcart_instructor"
CSRF_HEADER = "X-CSRF-Token"

# The cookie schemes document session authentication in OpenAPI. auto_error=False lets
# the checks below answer missing cookies with their own 401, after the origin check.
guest_cookie = APIKeyCookie(
    name=GUEST_COOKIE_NAME,
    scheme_name="GuestSession",
    description="HTTP-only cookie set by GET /api/v1/session.",
    auto_error=False,
)
instructor_cookie = APIKeyCookie(
    name=INSTRUCTOR_COOKIE_NAME,
    scheme_name="InstructorSession",
    description="HTTP-only cookie set by POST /api/v1/admin/login.",
    auto_error=False,
)
GuestToken = Annotated[str | None, Depends(guest_cookie)]
InstructorToken = Annotated[str | None, Depends(instructor_cookie)]
CsrfToken = Annotated[
    str | None,
    Header(
        alias=CSRF_HEADER,
        description="Required on state-changing requests: the csrf_token returned with the caller's session.",
    ),
]

router = APIRouter(tags=["identity"])


def require_same_origin(request: Request) -> None:
    """Reject requests a browser marks as coming from another site."""
    origin = request.headers.get("origin")
    if origin is not None and not _names_host(origin, request.headers.get("host")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-origin request refused.")
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request refused.")


@router.get("/session")
def start_guest_session(
    request: Request, response: Response, session: DbSession, token: GuestToken
) -> SessionView:
    """Return the caller's live guest session, or start a new guest session and set its cookie."""
    guest = ensure_guest(session, token)
    if guest.needs_cookie:
        _set_session_cookie(request, response, GUEST_COOKIE_NAME, guest.token, GUEST_SESSION_LIFETIME)
    response.headers["Cache-Control"] = "no-store"
    return SessionView(csrf_token=guest.csrf_token, expires_at=guest.expires_at)


@router.post("/admin/login", dependencies=[Depends(require_same_origin)])
def log_in(
    credentials: InstructorCredentials, request: Request, response: Response, session: DbSession
) -> SessionView:
    """Start an instructor session and set its cookie. Every failure is the same 401."""
    issued = log_in_instructor(session, credentials.username, credentials.password)
    if issued is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password.")
    _set_session_cookie(request, response, INSTRUCTOR_COOKIE_NAME, issued.token, INSTRUCTOR_SESSION_LIFETIME)
    response.headers["Cache-Control"] = "no-store"
    return SessionView(csrf_token=issued.csrf_token, expires_at=issued.expires_at)


def current_guest(session: DbSession, token: GuestToken) -> Guest:
    """Dependency for guest reads: the caller's live guest, or 401."""
    guest = find_live_guest(session, token)
    if guest is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "A live guest session is required; start one with GET /api/v1/session."
        )
    return guest


def guest_for_change(
    request: Request, session: DbSession, token: GuestToken, csrf_token: CsrfToken = None
) -> Guest:
    """Dependency for guest changes: same origin, then a live guest session, then its CSRF token."""
    require_same_origin(request)
    guest = current_guest(session, token)
    _require_csrf(token, csrf_token)
    return guest


def instructor_for_change(
    request: Request, session: DbSession, token: InstructorToken, csrf_token: CsrfToken = None
) -> InstructorSession:
    """Dependency for instructor changes: same origin, then a live instructor session, then its CSRF token."""
    require_same_origin(request)
    instructor_session = find_live_instructor_session(session, token)
    if instructor_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A live instructor session is required.")
    _require_csrf(token, csrf_token)
    return instructor_session


def _names_host(origin: str, host: str | None) -> bool:
    if not host:
        return False
    try:
        origin_host = urlsplit(origin).netloc
    except ValueError:
        return False
    return origin_host.lower() == host.lower()


def _require_csrf(session_token: str | None, presented: str | None) -> None:
    if session_token is None or not csrf_token_matches(session_token, presented):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token.")


def _set_session_cookie(request: Request, response: Response, name: str, token: str, lifetime: timedelta) -> None:
    settings: Settings = request.app.state.settings
    response.set_cookie(
        name,
        token,
        max_age=int(lifetime.total_seconds()),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
