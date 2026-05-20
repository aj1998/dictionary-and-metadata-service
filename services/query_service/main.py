from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .routers import query

logging.basicConfig(level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logging.info("Query service starting on port %s", settings.PORT)
    yield


app = FastAPI(title="Query Service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict:
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": "Not found"}},
    )


app.include_router(query.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.query_service.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=False,
    )
