"""Session tokens, CSRF tokens, password hashing, and guest/instructor session lookup.

Session tokens are random and opaque. The database stores only their SHA-256 hex
digest, so a database leak does not reveal usable cookies. Each session's CSRF
token is an HMAC derived from its own session token, so it cannot authorize any
other session. Expiry is always judged by the database clock.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cloudcart.identity.models import Guest, Instructor, InstructorSession

GUEST_SESSION_LIFETIME = timedelta(days=7)
INSTRUCTOR_SESSION_LIFETIME = timedelta(hours=8)
TOKEN_BYTES = 32
CSRF_CONTEXT = b"cloudcart-csrf-v1"

# Argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile: 64 MiB, 3 passes).
PASSWORD_HASHER = PasswordHasher()
# Verified when a login names an unknown user, so that path costs the same as a wrong password.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("cloudcart-unknown-user")


@dataclass(frozen=True)
class GuestSession:
    """A live guest session. `token` belongs only in the Set-Cookie header, never in a response body."""

    guest_id: UUID
    token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime
    needs_cookie: bool  # True when the token was just issued and must be sent with Set-Cookie


@dataclass(frozen=True)
class IssuedInstructorSession:
    """A new instructor session. `token` belongs only in the Set-Cookie header."""

    token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime


def new_session_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(session_token: str) -> str:
    """base64url(HMAC-SHA256(key=session token, msg=CSRF_CONTEXT)) without padding."""
    digest = hmac.new(session_token.encode(), CSRF_CONTEXT, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def csrf_token_matches(session_token: str, presented: str | None) -> bool:
    if presented is None:
        return False
    return hmac.compare_digest(csrf_token_for(session_token).encode(), presented.encode())


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except VerificationError:
        return False


def find_live_guest(session: Session, token: str | None) -> Guest | None:
    if not token:
        return None
    return session.scalars(
        select(Guest).where(Guest.token_hash == hash_session_token(token), Guest.expires_at > func.now())
    ).one_or_none()


def ensure_guest(session: Session, token: str | None) -> GuestSession:
    """Return the caller's live guest session, or start a new guest when the token is missing, unknown, or expired.

    An expired session is never extended: its guest and cart stay behind, and the caller
    becomes a new guest with an empty cart.
    """
    if token:
        guest = find_live_guest(session, token)
        if guest is not None:
            return _guest_session(guest, token, needs_cookie=False)
    token = new_session_token()
    guest = Guest(token_hash=hash_session_token(token), expires_at=func.now() + GUEST_SESSION_LIFETIME)
    session.add(guest)
    session.flush()
    return _guest_session(guest, token, needs_cookie=True)


def _guest_session(guest: Guest, token: str, needs_cookie: bool) -> GuestSession:
    return GuestSession(
        guest_id=guest.id,
        token=token,
        csrf_token=csrf_token_for(token),
        expires_at=guest.expires_at,
        needs_cookie=needs_cookie,
    )


def log_in_instructor(session: Session, username: str, password: str) -> IssuedInstructorSession | None:
    """Start an instructor session, or return None for any wrong username or password."""
    instructor = session.scalars(select(Instructor).where(Instructor.username == username)).one_or_none()
    if instructor is None:
        verify_password(DUMMY_PASSWORD_HASH, password)
        return None
    if not verify_password(instructor.password_hash, password):
        return None
    token = new_session_token()
    record = InstructorSession(
        instructor_id=instructor.id,
        token_hash=hash_session_token(token),
        expires_at=func.now() + INSTRUCTOR_SESSION_LIFETIME,
    )
    session.add(record)
    session.flush()
    return IssuedInstructorSession(token=token, csrf_token=csrf_token_for(token), expires_at=record.expires_at)


def find_live_instructor_session(session: Session, token: str | None) -> InstructorSession | None:
    if not token:
        return None
    return session.scalars(
        select(InstructorSession).where(
            InstructorSession.token_hash == hash_session_token(token), InstructorSession.expires_at > func.now()
        )
    ).one_or_none()
