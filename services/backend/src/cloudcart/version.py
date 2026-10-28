"""The running release, so the storefront can show which API version answers it."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["version"])


class VersionView(BaseModel):
    version: str


@router.get("/version")
def read_version(request: Request) -> VersionView:
    return VersionView(version=request.app.state.settings.release_version)
