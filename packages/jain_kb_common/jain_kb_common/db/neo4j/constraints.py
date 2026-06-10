from neo4j import AsyncDriver

_CONSTRAINTS = [
    "CREATE CONSTRAINT keyword_natural_key IF NOT EXISTS FOR (n:Keyword) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT topic_natural_key IF NOT EXISTS FOR (n:Topic) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT alias_text IF NOT EXISTS FOR (n:Alias) REQUIRE n.alias_text IS UNIQUE",
    "CREATE CONSTRAINT gatha_natural_key IF NOT EXISTS FOR (n:Gatha) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT shastra_natural_key IF NOT EXISTS FOR (n:Shastra) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT teeka_natural_key IF NOT EXISTS FOR (n:Teeka) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT publication_natural_key IF NOT EXISTS FOR (n:Publication) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT gatha_teeka_natural_key IF NOT EXISTS FOR (n:GathaTeeka) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT gatha_teeka_bhaavarth_natural_key IF NOT EXISTS FOR (n:GathaTeekaBhaavarth) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT kalash_natural_key IF NOT EXISTS FOR (n:Kalash) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT kalash_bhaavarth_natural_key IF NOT EXISTS FOR (n:KalashBhaavarth) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT page_natural_key IF NOT EXISTS FOR (n:Page) REQUIRE n.natural_key IS UNIQUE",
    "CREATE CONSTRAINT table_natural_key IF NOT EXISTS FOR (n:Table) REQUIRE n.natural_key IS UNIQUE",
]

_INDEXES = [
    "CREATE INDEX keyword_pg_id IF NOT EXISTS FOR (n:Keyword) ON (n.pg_id)",
    "CREATE INDEX topic_pg_id IF NOT EXISTS FOR (n:Topic) ON (n.pg_id)",
    "CREATE INDEX teeka_pg_id IF NOT EXISTS FOR (n:Teeka) ON (n.pg_id)",
    "CREATE INDEX publication_pg_id IF NOT EXISTS FOR (n:Publication) ON (n.pg_id)",
    "CREATE INDEX kalash_pg_id IF NOT EXISTS FOR (n:Kalash) ON (n.pg_id)",
    "CREATE INDEX topic_kw_path IF NOT EXISTS FOR (n:Topic) ON (n.parent_keyword_natural_key, n.topic_path)",
    "CREATE INDEX keyword_is_stub IF NOT EXISTS FOR (n:Keyword) ON (n.is_stub)",
    "CREATE INDEX topic_is_stub IF NOT EXISTS FOR (n:Topic) ON (n.is_stub)",
    "CREATE INDEX gatha_is_stub IF NOT EXISTS FOR (n:Gatha) ON (n.is_stub)",
    "CREATE INDEX gatha_teeka_is_stub IF NOT EXISTS FOR (n:GathaTeeka) ON (n.is_stub)",
    "CREATE INDEX gatha_teeka_bhaavarth_is_stub IF NOT EXISTS FOR (n:GathaTeekaBhaavarth) ON (n.is_stub)",
    "CREATE INDEX kalash_is_stub IF NOT EXISTS FOR (n:Kalash) ON (n.is_stub)",
    "CREATE INDEX kalash_bhaavarth_is_stub IF NOT EXISTS FOR (n:KalashBhaavarth) ON (n.is_stub)",
    "CREATE INDEX page_is_stub IF NOT EXISTS FOR (n:Page) ON (n.is_stub)",
    "CREATE INDEX table_pg_id IF NOT EXISTS FOR (n:Table) ON (n.pg_id)",
    "CREATE INDEX table_is_stub IF NOT EXISTS FOR (n:Table) ON (n.is_stub)",
    "CREATE INDEX table_parent IF NOT EXISTS FOR (n:Table) ON (n.parent_natural_key)",
    "CREATE INDEX table_type IF NOT EXISTS FOR (n:Table) ON (n.table_type)",
]


async def ensure_constraints(driver: AsyncDriver, database: str = "jainkb") -> None:
    async with driver.session(database=database) as session:
        for cypher in _CONSTRAINTS + _INDEXES:
            await session.run(cypher)
