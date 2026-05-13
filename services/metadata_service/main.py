from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .routers import (
    admin_search,
    anuyogas,
    authors,
    books,
    pravachans,
    publications,
    publishers,
    shastras,
    teekas,
)

logging.basicConfig(level=settings.LOG_LEVEL)


def _load_publishers() -> list[dict]:
    base = os.path.dirname(__file__)
    path = os.path.join(
        base, "..", "..", "parser_configs", "_manual_configs", "publishers.json"
    )
    path = os.path.normpath(path)
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.publishers = _load_publishers()
    yield


app = FastAPI(title="Metadata Service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict:
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Not found"}})


app.include_router(authors.router)
app.include_router(shastras.router)
app.include_router(anuyogas.router)
app.include_router(teekas.router)
app.include_router(publications.router)
app.include_router(publishers.router)
app.include_router(books.router)
app.include_router(pravachans.router)
app.include_router(admin_search.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.metadata_service.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
