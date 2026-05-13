from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1", tags=["publishers"])


class PublisherEntry(BaseModel):
    publisher_id: str
    publisher: str


@router.get("/publishers", response_model=list[PublisherEntry])
async def list_publishers(request: Request) -> list[PublisherEntry]:
    publishers: list[dict] = request.app.state.publishers
    return [PublisherEntry(**p) for p in publishers]
