from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .deps import _get_factory, get_neo4j_driver

from .domains.metadata.routers import (
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
from .domains.data.routers import (
    browse,
    extract_matches,
    gathas,
    kalashas,
    keywords as data_keywords,
    search,
    stats,
    topics as data_topics,
)
from .domains.navigation.routers import (
    admin as nav_admin,
    graph,
    keywords as nav_keywords,
    topics as nav_topics,
)

logging.basicConfig(level=settings.LOG_LEVEL)

_node_count_cache: tuple[int, float] | None = None
_NODE_COUNT_TTL = 300.0


def _load_publishers() -> list[dict]:
    base = os.path.dirname(__file__)
    path = os.path.normpath(
        os.path.join(base, "..", "..", "parser_configs", "_manual_configs", "publishers.json")
    )
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.publishers = _load_publishers()
    driver = get_neo4j_driver()
    logging.info("Core service using Neo4j database: %s", settings.NEO4J_DATABASE)
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            await session.run("RETURN 1")
    except Exception as exc:
        logging.warning("Neo4j not reachable on startup: %s", exc)
    yield
    await driver.close()


app = FastAPI(title="Core Service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict:
    global _node_count_cache
    neo4j_status, postgres_status, node_count = "ok", "ok", 0
    driver = get_neo4j_driver()
    try:
        now = time.monotonic()
        if _node_count_cache and _node_count_cache[1] > now:
            node_count = _node_count_cache[0]
        else:
            async with driver.session(database=settings.NEO4J_DATABASE) as session:
                result = await session.run("MATCH (n) RETURN count(n) AS cnt")
                record = await result.single()
                node_count = int(record["cnt"]) if record else 0
            _node_count_cache = (node_count, now + _NODE_COUNT_TTL)
    except Exception:
        neo4j_status = "error"

    try:
        factory = _get_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        postgres_status = "error"

    return {
        "status": "ok",
        "neo4j": neo4j_status,
        "postgres": postgres_status,
        "graph_node_count": node_count,
    }


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Not found"}})


for r in (
    authors.router,
    shastras.router,
    anuyogas.router,
    teekas.router,
    publications.router,
    publishers.router,
    books.router,
    pravachans.router,
    admin_search.router,
):
    app.include_router(r)

for r in (
    data_keywords.router,
    data_topics.router,
    gathas.router,
    kalashas.router,
    extract_matches.router,
    browse.router,
    search.router,
    stats.router,
):
    app.include_router(r)

for r in (nav_keywords.router, nav_topics.router, graph.router, nav_admin.router):
    app.include_router(r)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.core_service.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
