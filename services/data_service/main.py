from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .routers import browse, gathas, kalashas, keywords, search, stats, topics

logging.basicConfig(level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(title="Data Service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict:
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Not found"}})


app.include_router(keywords.router)
app.include_router(topics.router)
app.include_router(gathas.router)
app.include_router(kalashas.router)
app.include_router(browse.router)
app.include_router(search.router)
app.include_router(stats.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.data_service.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
