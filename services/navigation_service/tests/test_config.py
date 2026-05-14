from __future__ import annotations

import importlib


def test_neo4j_use_default_database_env_switch(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/test")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("NEO4J_DATABASE", "jainkb")
    monkeypatch.setenv("NEO4J_USE_DEFAULT_DATABASE", "true")

    from services.navigation_service import config

    importlib.reload(config)

    assert config.settings.NEO4J_DATABASE == "neo4j"
