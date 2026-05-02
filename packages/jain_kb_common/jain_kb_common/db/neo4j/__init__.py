import os

from neo4j import AsyncGraphDatabase, AsyncDriver

_driver: AsyncDriver | None = None


def get_driver(
    url: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> AsyncDriver:
    global _driver
    if _driver is None:
        url = url or os.environ["NEO4J_URL"]
        user = user or os.environ.get("NEO4J_USER", "neo4j")
        password = password or os.environ["NEO4J_PASSWORD"]
        _driver = AsyncGraphDatabase.driver(url, auth=(user, password))
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
