from neo4j import AsyncDriver

_CONSTRAINTS = [
    "CREATE CONSTRAINT keyword_natural_key IF NOT EXISTS FOR (n:Keyword) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT topic_natural_key IF NOT EXISTS FOR (n:Topic) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT alias_text IF NOT EXISTS FOR (n:Alias) REQUIRE n.alias_text IS UNIQUE",
    "CREATE CONSTRAINT gatha_natural_key IF NOT EXISTS FOR (n:Gatha) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT shastra_natural_key IF NOT EXISTS FOR (n:Shastra) REQUIRE n.natural_key IS UNIQUE",
]

_INDEXES = [
    "CREATE INDEX keyword_pg_id IF NOT EXISTS FOR (n:Keyword) ON (n.pg_id)",
    "CREATE INDEX topic_pg_id IF NOT EXISTS FOR (n:Topic) ON (n.pg_id)",
]


async def ensure_constraints(driver: AsyncDriver, database: str = "jainkb") -> None:
    async with driver.session(database=database) as session:
        for cypher in _CONSTRAINTS + _INDEXES:
            await session.run(cypher)
