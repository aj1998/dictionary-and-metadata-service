from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .deps import get_neo4j_driver
from .routers import graph, keywords, topics, admin

logging.basicConfig(level=settings.LOG_LEVEL)

# In-process node count cache: (count, expires_at)
_node_count_cache: tuple[int, float] | None = None
_NODE_COUNT_TTL = 300.0  # 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Verify Neo4j connectivity on startup
    driver = get_neo4j_driver()
    logging.info("Navigation service using Neo4j database: %s", settings.NEO4J_DATABASE)
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            await session.run("RETURN 1")
    except Exception as exc:
        logging.warning("Neo4j not reachable on startup: %s", exc)
    yield
    await driver.close()


app = FastAPI(title="Navigation Service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict:
    global _node_count_cache
    neo4j_status = "ok"
    postgres_status = "ok"
    node_count = 0

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
        from .deps import _get_factory
        factory = _get_factory()
        from sqlalchemy import text
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


app.include_router(keywords.router)
app.include_router(topics.router)
app.include_router(graph.router)
app.include_router(admin.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.navigation_service.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
