from __future__ import annotations

from scripts.ingest_goldens_apply import _ensure_postgres_extensions, _POSTGRES_EXTENSION_STMTS


class _FakeConn:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, stmt) -> None:
        self.calls.append(str(stmt))


async def test_ensure_postgres_extensions_runs_required_statements() -> None:
    conn = _FakeConn()

    await _ensure_postgres_extensions(conn)

    assert conn.calls == list(_POSTGRES_EXTENSION_STMTS)
