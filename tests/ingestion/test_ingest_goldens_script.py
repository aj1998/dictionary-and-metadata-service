from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from scripts import ingest_goldens_apply


def test_golden_specs_match_apply_tests():
    assert [spec.keyword for spec in ingest_goldens_apply.GOLDENS] == [
        "आत्मा",
        "द्रव्य",
        "पर्याय",
        "वस्तु",
    ]


def test_dry_run_summarizes_selected_goldens(capsys):
    exit_code = ingest_goldens_apply.main(["--dry-run", "--keyword", "आत्मा"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "आत्मा" in captured.out
    assert "would apply 1 golden" in captured.out


def test_clear_first_runs_before_apply(monkeypatch):
    calls: list[str] = []

    async def fake_clear(**kwargs):
        calls.append("clear")
        assert kwargs["neo4j_database"] == "neo4j"

    async def fake_apply(selected, *, neo4j_database, ingestion_run_id):
        calls.append("apply")
        assert len(selected) == 1
        assert neo4j_database == "neo4j"
        assert ingestion_run_id is None

    monkeypatch.setattr(ingest_goldens_apply, "_clear_existing_data", fake_clear)
    monkeypatch.setattr(ingest_goldens_apply, "_run_apply", fake_apply)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example")
    monkeypatch.setenv("NEO4J_URL", "bolt://example")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    exit_code = ingest_goldens_apply.main(["--clear-first", "--keyword", "आत्मा"])

    assert exit_code == 0
    assert calls == ["clear", "apply"]


def test_apply_bootstraps_postgres_schema(monkeypatch):
    calls: list[str] = []

    class FakeConn:
        async def run_sync(self, fn):
            calls.append(fn.__name__)

    class FakeEngine:
        @asynccontextmanager
        async def begin(self):
            yield FakeConn()

        async def dispose(self):
            calls.append("dispose")

    class FakeMongoClient:
        def __init__(self, *_args, **_kwargs):
            self._db = SimpleNamespace()

        def __getitem__(self, _name):
            return SimpleNamespace()

        def close(self):
            calls.append("mongo_close")

    class FakeSession:
        async def execute(self, *_args, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeFactory:
        def __call__(self, *args, **kwargs):
            return FakeSession()

    class FakeDriver:
        @asynccontextmanager
        async def session(self, database):
            yield SimpleNamespace(run=lambda *_args, **_kwargs: None)

    async def fake_apply(*args, **kwargs):
        calls.append("apply")

    async def fake_constraints(*args, **kwargs):
        calls.append("constraints")

    monkeypatch.setattr(ingest_goldens_apply, "create_async_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(ingest_goldens_apply, "async_sessionmaker", lambda *args, **kwargs: FakeFactory())
    monkeypatch.setattr(ingest_goldens_apply, "AsyncIOMotorClient", FakeMongoClient)
    monkeypatch.setattr(ingest_goldens_apply, "get_driver", lambda *args, **kwargs: FakeDriver())
    monkeypatch.setattr(ingest_goldens_apply, "ensure_constraints", fake_constraints)
    monkeypatch.setattr(ingest_goldens_apply, "apply_approved_keyword_payload", fake_apply)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example")
    monkeypatch.setenv("NEO4J_URL", "bolt://example")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    exit_code = ingest_goldens_apply.main(["--keyword", "आत्मा"])

    assert exit_code == 0
    assert "create_all" in calls
    assert "apply" in calls
