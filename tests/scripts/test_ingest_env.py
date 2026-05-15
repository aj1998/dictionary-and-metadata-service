from __future__ import annotations

import os


def test_mongo_db_name_takes_precedence(monkeypatch):
    monkeypatch.setenv("MONGO_DB_NAME", "mydb")
    monkeypatch.setenv("MONGO_DB", "other")
    resolved = os.environ.get("MONGO_DB_NAME") or os.environ.get("MONGO_DB", "jain_kb")
    assert resolved == "mydb"


def test_mongo_db_fallback_to_mongo_db(monkeypatch):
    monkeypatch.delenv("MONGO_DB_NAME", raising=False)
    monkeypatch.setenv("MONGO_DB", "fallback")
    resolved = os.environ.get("MONGO_DB_NAME") or os.environ.get("MONGO_DB", "jain_kb")
    assert resolved == "fallback"


def test_mongo_db_default_is_jain_kb(monkeypatch):
    monkeypatch.delenv("MONGO_DB_NAME", raising=False)
    monkeypatch.delenv("MONGO_DB", raising=False)
    resolved = os.environ.get("MONGO_DB_NAME") or os.environ.get("MONGO_DB", "jain_kb")
    assert resolved == "jain_kb"
