"""Request and response bodies for session bootstrap and instructor login."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

from cloudcart.identity.models import USERNAME_MAX_LENGTH

PASSWORD_MAX_LENGTH = 256

# PostgreSQL returns timestamps in the connection's time zone; responses always use UTC.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


class SessionView(BaseModel):
    """A live session's CSRF token. The session token itself travels only in its HTTP-only cookie."""

    csrf_token: str = Field(description="Send as the X-CSRF-Token header on every state-changing request.")
    expires_at: UtcDatetime


class InstructorCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: str = Field(min_length=1, max_length=USERNAME_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
