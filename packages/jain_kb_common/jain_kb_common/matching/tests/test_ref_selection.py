"""
Tests for pick_refs_to_show / pick_hidden_refs — mirrors DefinitionModal.test.ts
fixtures to ensure identical selection behaviour between the TS and Python ports.
"""

import pytest

from jain_kb_common.matching.ref_selection import pick_hidden_refs, pick_refs_to_show


# ── fixtures ──────────────────────────────────────────────────────────────────

def make_ref(**overrides) -> dict:
    base = {
        "text": "",
        "inline_reference": False,
        "needs_manual_match": False,
        "is_teeka": False,
        "teeka_name": "",
        "shastra_name": None,
        "match_method": None,
        "resolved_fields": [{"field": "गाथा", "value": "10"}],
    }
    base.update(overrides)
    return base


# ── pick_refs_to_show ─────────────────────────────────────────────────────────

def test_empty_references_returns_empty():
    assert pick_refs_to_show([]) == []


def test_single_non_inline_ref_with_fields_returned():
    ref = make_ref(inline_reference=False)
    assert pick_refs_to_show([ref]) == [ref]


def test_all_non_inline_refs_returned():
    ref1 = make_ref(inline_reference=False, shastra_name="समयसार")
    ref2 = make_ref(inline_reference=False, shastra_name="नियमसार")
    result = pick_refs_to_show([ref1, ref2])
    assert len(result) == 2
    assert ref1 in result
    assert ref2 in result


def test_non_inline_ref_without_fields_excluded():
    with_fields = make_ref(inline_reference=False)
    no_fields = make_ref(inline_reference=False, resolved_fields=[])
    result = pick_refs_to_show([with_fields, no_fields])
    assert result == [with_fields]
    assert no_fields not in result


def test_all_non_inline_refs_have_no_fields_returns_empty():
    # Non-inline refs exist but none have resolved_fields → empty (no inline fallback)
    no_fields = make_ref(inline_reference=False, resolved_fields=[])
    inline_ref = make_ref(inline_reference=True)
    result = pick_refs_to_show([no_fields, inline_ref])
    # TS: if nonInline.length > 0 → return filtered non-inline (which is [])
    assert result == []


def test_fallback_to_first_inline_when_no_non_inline():
    inline1 = make_ref(inline_reference=True, shastra_name="समयसार")
    inline2 = make_ref(inline_reference=True, shastra_name="नियमसार")
    result = pick_refs_to_show([inline1, inline2])
    assert result == [inline1]


def test_fallback_inline_only_qualifying():
    # First inline has no resolved_fields; second does → return second only
    no_fields = make_ref(inline_reference=True, resolved_fields=[])
    with_fields = make_ref(inline_reference=True, shastra_name="समयसार")
    result = pick_refs_to_show([no_fields, with_fields])
    assert result == [with_fields]


def test_prefers_non_inline_over_inline():
    non_inline = make_ref(inline_reference=False, shastra_name="समयसार")
    inline_ref = make_ref(inline_reference=True, shastra_name="नियमसार")
    result = pick_refs_to_show([non_inline, inline_ref])
    assert result == [non_inline]


def test_shastra_and_teeka_refs_both_shown():
    shastra_ref = make_ref(inline_reference=False, is_teeka=False, shastra_name="समयसार")
    teeka_ref = make_ref(inline_reference=False, is_teeka=True, shastra_name="समयसार", teeka_name="टीका")
    result = pick_refs_to_show([shastra_ref, teeka_ref])
    assert len(result) == 2
    assert shastra_ref in result
    assert teeka_ref in result


# ── pick_hidden_refs ──────────────────────────────────────────────────────────

def test_hidden_empty_when_no_refs():
    assert pick_hidden_refs([]) == []


def test_hidden_empty_when_only_non_inline():
    ref = make_ref(inline_reference=False)
    assert pick_hidden_refs([ref]) == []


def test_hidden_contains_inline_when_non_inline_shown():
    non_inline = make_ref(inline_reference=False, shastra_name="समयसार")
    inline = make_ref(inline_reference=True, shastra_name="नियमसार")
    hidden = pick_hidden_refs([non_inline, inline])
    assert hidden == [inline]


def test_hidden_contains_extra_inline_refs():
    first = make_ref(inline_reference=True, shastra_name="समयसार")
    second = make_ref(inline_reference=True, shastra_name="नियमसार")
    third = make_ref(inline_reference=True, shastra_name="parवचनसार".replace("par", "प्र"))
    hidden = pick_hidden_refs([first, second, third])
    assert len(hidden) == 2
    assert second in hidden
    assert third in hidden
    assert first not in hidden


def test_hidden_excludes_refs_with_no_fields():
    non_inline = make_ref(inline_reference=False)
    inline_no_fields = make_ref(inline_reference=True, resolved_fields=[])
    hidden = pick_hidden_refs([non_inline, inline_no_fields])
    assert hidden == []


def test_hidden_plus_shown_equals_all_with_fields():
    ref1 = make_ref(inline_reference=False, shastra_name="अ")
    ref2 = make_ref(inline_reference=True, shastra_name="ब")
    ref3 = make_ref(inline_reference=True, shastra_name="क", resolved_fields=[])
    refs = [ref1, ref2, ref3]
    shown = pick_refs_to_show(refs)
    hidden = pick_hidden_refs(refs)
    all_with_fields = [r for r in refs if r.get("resolved_fields", [])]
    assert sorted(id(r) for r in shown + hidden) == sorted(id(r) for r in all_with_fields)


def test_hidden_multiple_inline_hidden_when_non_inline_shown():
    non_inline = make_ref(inline_reference=False, shastra_name="समयसार")
    inline1 = make_ref(inline_reference=True, shastra_name="नियमसार")
    inline2 = make_ref(inline_reference=True, shastra_name="parवचनसार".replace("par", "प्र"))
    hidden = pick_hidden_refs([non_inline, inline1, inline2])
    assert len(hidden) == 2
    assert inline1 in hidden
    assert inline2 in hidden


# ── identity semantics (same object, not equality) ───────────────────────────

def test_shown_uses_identity_not_equality():
    # Two structurally equal refs — only one should be in shown, the other hidden
    ref_a = make_ref(inline_reference=True, shastra_name="समयसार")
    ref_b = make_ref(inline_reference=True, shastra_name="समयसार")  # same values, different object
    refs = [ref_a, ref_b]
    shown = pick_refs_to_show(refs)
    hidden = pick_hidden_refs(refs)
    assert len(shown) == 1
    assert len(hidden) == 1
    # shown contains ref_a (first), hidden contains ref_b
    assert shown[0] is ref_a
    assert hidden[0] is ref_b
