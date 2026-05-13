"""Token → keyword natural_key resolution using Postgres.

Two-pass strategy per spec:
  1. Exact match on keywords.natural_key
  2. Alias match on keyword_aliases.alias_text
  3. Both passes repeated after a light Hindi-suffix strip
"""
from __future__ import annotations

import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.postgres.keywords import Keyword, KeywordAlias

# Devanagari matras and combining marks that are stripped as "suffixes"
_STRIP_CHARS = frozenset(
    "ा"  # ा  aa
    "ि"  # ि  i
    "ी"  # ी  ii
    "ु"  # ु  u
    "ू"  # ू  uu
    "ृ"  # ृ  ri
    "े"  # े  e
    "ै"  # ै  ai
    "ो"  # ो  o
    "ौ"  # ौ  au
    "ं"  # ं  anusvara
    "ः"  # ः  visarga
    "्"  # ्  virama/halant
    "ॐ"  # ॐ  om (edge case)
    "m"       # trailing nasal in transliterated forms
)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def strip_suffix(token: str) -> str | None:
    """Remove one trailing Devanagari matra/combining mark. Returns None if nothing to strip."""
    if not token:
        return None
    last = token[-1]
    if last in _STRIP_CHARS:
        stripped = token[:-1]
        return stripped if stripped else None
    return None


async def _exact_match(session: AsyncSession, token: str) -> str | None:
    result = await session.execute(
        select(Keyword.natural_key).where(Keyword.natural_key == token)
    )
    return result.scalar_one_or_none()


async def _alias_match(session: AsyncSession, token: str) -> str | None:
    result = await session.execute(
        select(Keyword.natural_key)
        .join(KeywordAlias, KeywordAlias.keyword_id == Keyword.id)
        .where(KeywordAlias.alias_text == token)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_token(
    session: AsyncSession,
    token: str,
) -> tuple[str | None, str]:
    """Resolve a token to a keyword natural_key.

    Returns (matched_natural_key, match_kind) where match_kind is one of:
    "exact", "alias", "suffix_strip", "none".
    """
    normalized = _nfc(token)

    # Pass 1: exact keyword match
    nk = await _exact_match(session, normalized)
    if nk is not None:
        return nk, "exact"

    # Pass 2: alias match
    nk = await _alias_match(session, normalized)
    if nk is not None:
        return nk, "alias"

    # Pass 3 & 4: same two lookups after suffix strip
    stripped = strip_suffix(normalized)
    if stripped:
        nk = await _exact_match(session, stripped)
        if nk is not None:
            return nk, "suffix_strip"

        nk = await _alias_match(session, stripped)
        if nk is not None:
            return nk, "suffix_strip"

    return None, "none"
