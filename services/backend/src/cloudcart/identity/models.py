"""Guest sessions, the instructor account, and instructor sessions.

Session tables store only the SHA-256 hex digest of each session token; the raw
token exists only in the client's cookie.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from cloudcart.db import Base

TOKEN_HASH_LENGTH = 64  # hex SHA-256
USERNAME_MAX_LENGTH = 64


class Guest(Base):
    """An anonymous shopper. A guest lives exactly as long as its session; expiry is final."""

    __tablename__ = "guests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Instructor(Base):
    """The seeded instructor account. Only an Argon2id password hash is stored."""

    __tablename__ = "instructors"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class InstructorSession(Base):
    __tablename__ = "instructor_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    instructor_id: Mapped[UUID] = mapped_column(ForeignKey(Instructor.id, ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
