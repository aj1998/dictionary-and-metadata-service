from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def seeded_entities(client: AsyncClient):
    from jain_kb_common.db.postgres.authors import Author
    from jain_kb_common.db.postgres.enums import AuthorKind, IngestionSource, IngestionRunStatus
    from jain_kb_common.db.postgres.gathas import Gatha
    from jain_kb_common.db.postgres.ingestion import IngestionRun
    from jain_kb_common.db.postgres.keywords import Keyword
    from jain_kb_common.db.postgres.shastras import Shastra
    from jain_kb_common.db.postgres.topics import Topic

    async with client.state() as session:  # type: ignore[attr-defined]
        author = Author(
            natural_key="kundkund",
            display_name={"lang": "hi", "script": "devanagari", "text": "कुन्दकुन्द"},
            kind=AuthorKind.acharya,
        )
        session.add(author)
        await session.flush()

        shastra = Shastra(
            natural_key="samaysaar",
            title={"lang": "hi", "script": "devanagari", "text": "समयसार"},
            author_id=author.id,
        )
        session.add(shastra)

        kw1 = Keyword(natural_key="आत्मा", display_text="आत्मा", source_url=None)
        kw2 = Keyword(natural_key="कर्म", display_text="कर्म", source_url=None)
        session.add_all([kw1, kw2])
        await session.flush()

        session.add_all(
            [
                Topic(
                    natural_key="atma-bhed",
                    display_text={"lang": "hi", "script": "devanagari", "text": "आत्मा के भेद"},
                    source=IngestionSource.jainkosh,
                    parent_keyword_id=kw1.id,
                    topic_path="आत्मा/भेद",
                    is_leaf=True,
                    is_synthetic=False,
                ),
                Topic(
                    natural_key="karma-bhed",
                    display_text={"lang": "hi", "script": "devanagari", "text": "कर्म के भेद"},
                    source=IngestionSource.jainkosh,
                    parent_keyword_id=kw2.id,
                    topic_path="कर्म/भेद",
                    is_leaf=True,
                    is_synthetic=False,
                ),
            ]
        )

        session.add(
            Gatha(
                natural_key="samaysaar:001",
                shastra_id=shastra.id,
                gatha_number="001",
            )
        )

        session.add_all(
            [
                IngestionRun(
                    source=IngestionSource.jainkosh,
                    triggered_by="test",
                    status=IngestionRunStatus.success,
                    started_at=datetime.now(timezone.utc) - timedelta(days=2),
                    finished_at=datetime.now(timezone.utc) - timedelta(days=2) + timedelta(minutes=1),
                    stats={"entities_touched": 7},
                ),
                IngestionRun(
                    source=IngestionSource.nj,
                    triggered_by="test",
                    status=IngestionRunStatus.success,
                    started_at=datetime.now(timezone.utc) - timedelta(days=1),
                    finished_at=datetime.now(timezone.utc) - timedelta(days=1) + timedelta(minutes=1),
                    stats={"entities_touched": 11},
                ),
            ]
        )

        await session.commit()


class TestStatsCounts:
    async def test_counts_endpoint_returns_aggregates(self, client: AsyncClient, seeded_entities):
        r = await client.get("/v1/stats/counts")

        assert r.status_code == 200
        assert r.json() == {
            "shastras": 1,
            "gathas": 1,
            "topics": 2,
            "keywords": 2,
        }


class TestActivityRecent:
    async def test_recent_activity_returns_latest_first(self, client: AsyncClient, seeded_entities):
        r = await client.get("/v1/activity/recent")

        assert r.status_code == 200
        payload = r.json()
        assert len(payload) == 2
        assert payload[0]["source"] == "nj"
        assert payload[0]["entities_touched"] == 11
        assert payload[1]["source"] == "jainkosh"
        assert payload[1]["entities_touched"] == 7
        assert "run_at" in payload[0]
        assert "id" in payload[0]
