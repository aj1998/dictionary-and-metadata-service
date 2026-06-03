import os

import pytest

from jain_kb_common.matching.score import (
    DEFAULT_THRESHOLD,
    KIND_THRESHOLDS,
    jaccard,
    threshold_for,
)


# ── DEFAULT_THRESHOLD ─────────────────────────────────────────────────────────

def test_default_threshold_value():
    assert DEFAULT_THRESHOLD == 0.80


# ── KIND_THRESHOLDS ───────────────────────────────────────────────────────────

def test_kind_thresholds_prakrit_gatha():
    assert KIND_THRESHOLDS["prakrit_gatha"] == 0.90


def test_kind_thresholds_sanskrit_gatha():
    assert KIND_THRESHOLDS["sanskrit_gatha"] == 0.90


def test_kind_thresholds_hindi_gatha():
    assert KIND_THRESHOLDS["hindi_gatha"] == 0.85


def test_kind_thresholds_text_kinds():
    for kind in ("prakrit_text", "sanskrit_text", "hindi_text"):
        assert KIND_THRESHOLDS[kind] == 0.80


# ── threshold_for ─────────────────────────────────────────────────────────────

def test_threshold_for_returns_kind_value():
    assert threshold_for("prakrit_gatha") == 0.90
    assert threshold_for("hindi_gatha") == 0.85
    assert threshold_for("hindi_text") == 0.80


def test_threshold_for_unknown_kind_returns_default():
    # 'see_also' and 'table' are not in KIND_THRESHOLDS
    assert threshold_for("see_also") == DEFAULT_THRESHOLD  # type: ignore[arg-type]


def test_threshold_for_env_override(monkeypatch):
    monkeypatch.setenv("MATCHER_THRESHOLD_PRAKRIT_GATHA", "0.70")
    assert threshold_for("prakrit_gatha") == pytest.approx(0.70)


def test_threshold_for_env_override_hindi_text(monkeypatch):
    monkeypatch.setenv("MATCHER_THRESHOLD_HINDI_TEXT", "0.95")
    assert threshold_for("hindi_text") == pytest.approx(0.95)


def test_threshold_for_without_env_override(monkeypatch):
    monkeypatch.delenv("MATCHER_THRESHOLD_PRAKRIT_GATHA", raising=False)
    assert threshold_for("prakrit_gatha") == 0.90


# ── jaccard ───────────────────────────────────────────────────────────────────

def test_jaccard_identical_sets():
    assert jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_jaccard_disjoint_sets():
    assert jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial_overlap():
    # |{a,b} ∩ {b,c}| / |{a,b,c}| = 1/3
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_jaccard_empty_both():
    assert jaccard(set(), set()) == 1.0


def test_jaccard_one_empty():
    assert jaccard({"a"}, set()) == 0.0
    assert jaccard(set(), {"a"}) == 0.0


def test_jaccard_subset():
    # b ⊂ a → |b| / |a|
    assert jaccard({"a", "b", "c"}, {"a"}) == pytest.approx(1 / 3)


def test_jaccard_symmetry():
    a = {"x", "y", "z"}
    b = {"y", "z", "w"}
    assert jaccard(a, b) == jaccard(b, a)


def test_jaccard_returns_float():
    result = jaccard({"a"}, {"a"})
    assert isinstance(result, float)
