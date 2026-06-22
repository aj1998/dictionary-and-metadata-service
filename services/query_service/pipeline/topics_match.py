from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from jain_kb_common.db.mongo.collections import TOPIC_EXTRACTS
from jain_kb_common.hydration.topic_extracts import (
    count_displayable_extract_blocks,
    extract_references,
    hydrate_topic_extracts_hi,
)

logger = logging.getLogger(__name__)
LEAF_SCORE_FACTOR = 1.0
CONTAINER_SCORE_FACTOR = 0.6

# Characters stripped when normalizing a topic path / query token for the
# token-coverage guard: halant/virama, ZWNJ/ZWJ, path separators, hyphens,
# whitespace and Devanagari dandas. Stripping the halant lets tokens like
# ``सत्`` match ``सत`` and folds conjuncts so a token matches regardless of the
# combining form used in the natural_key. The SAME class is applied in Python
# (token side) and SQL (natural_key side) so substring containment is reliable.
_NORM_STRIP_CHARS = "्‌‍/\\-:।॥|"
_NORM_STRIP_RE = re.compile(f"[{re.escape(_NORM_STRIP_CHARS)}\\s]")

# In-word characters removed but which do NOT split a word: halant/virama and
# the ZWNJ/ZWJ joiners. Used (in SQL) to normalize each path *segment* while
# keeping segment boundaries intact, so coverage can match at word boundaries.
_INWORD_STRIP_RE_SQL = "[्‌‍]"
# Path-segment delimiters: ``: / -`` (the natural_key encodings), Devanagari
# dandas and whitespace. Splitting on these yields the individual Hindi words of
# the topic path so a query token must match a word *prefix* — preventing e.g.
# ``सत`` from spuriously matching the middle of ``पंचास्तिकाय`` (पंचा-स्ति-काय).
_SEG_SPLIT_RE_SQL = "[[:space:]/:।॥|-]+"

# Common Hindi connectives/postpositions that carry no topical signal. Excluded
# from the coverage token set so phrase queries like "सत् व द्रव्य" are not
# diluted by the "व".
_COVERAGE_STOPWORDS = {
    "व", "और", "या", "के", "का", "की", "को", "में", "से", "पर",
    "है", "हैं", "तथा", "एवं", "तो", "ही", "भी",
}


def normalize_topic_token(token: str) -> str:
    """Normalize a token/path fragment for coverage comparison.

    Lowercases (no-op for Devanagari, helps incidental latin), then removes
    halants, joiners, separators, hyphens, dandas and whitespace.
    """
    return _NORM_STRIP_RE.sub("", token.strip().lower())


def build_coverage_tokens(raw_tokens: list[str]) -> list[str]:
    """Turn raw query tokens into the de-duplicated, normalized set used by the
    coverage guard. Drops stopwords and tokens too short to be meaningful."""
    out: list[str] = []
    for raw in raw_tokens:
        if raw.strip() in _COVERAGE_STOPWORDS:
            continue
        norm = normalize_topic_token(raw)
        if len(norm) >= 2:
            out.append(norm)
    return list(dict.fromkeys(out))


@dataclass
class TopicTrigramHit:
    topic_pg_id: str
    natural_key: str
    display_text: object  # raw JSONB
    is_leaf: bool
    source: str
    # On input this is the raw GREATEST(trigram, substring) value; in
    # ``__post_init__`` it is folded with ``token_coverage`` so the reported
    # ``similarity`` is the coverage-weighted match strength. This is deliberate:
    # the topics search UI ranks and shows ``similarity`` directly as "% मिलान",
    # so weighting it here (backend-only) is what lifts full-coverage child
    # topics above topics that share only an incidental token — without any UI
    # change. ``raw_similarity`` keeps the unweighted trigram value for callers
    # that need it.
    similarity: float
    # Fraction of meaningful query tokens present (normalized substring) in the
    # topic's natural_key path. 1.0 when the guard is disabled / no tokens.
    token_coverage: float = 1.0
    raw_similarity: float = field(init=False)
    score: float = field(init=False)

    def __post_init__(self) -> None:
        factor = LEAF_SCORE_FACTOR if self.is_leaf else CONTAINER_SCORE_FACTOR
        self.raw_similarity = self.similarity
        # Fold coverage into the displayed/ranking similarity.
        self.similarity = self.similarity * self.token_coverage
        # score additionally applies the leaf/container weighting (used by the
        # chat merge with graphrag; the UI uses similarity).
        self.score = self.similarity * factor


def get_display_text_hi(display_text: object) -> str:
    """Extract Hindi text from the display_text JSONB field."""
    if display_text is None:
        return ""
    if isinstance(display_text, dict):
        display_text = [display_text]
    for item in (display_text or []):
        if isinstance(item, dict) and item.get("lang") in ("hin", "hi"):
            return item.get("text", "")
    return ""


def ancestors_from_natural_key(natural_key: str) -> list[str]:
    """Return the human-readable ancestor segments of a topic natural_key.

    Real jainkosh topic keys are colon-separated with kebab-cased Hindi
    segments (e.g. ``द्रव्य:द्रव्य-के-भेद-व-लक्षण:...``); legacy/spec keys use
    ``/`` (e.g. ``द्रव्य/स्वतंत्रता/लक्षण``). We pick whichever separator is
    present (preferring ``:``), drop the leaf segment, and turn ``-`` back into
    spaces so the breadcrumb reads naturally.
    """
    sep = ":" if ":" in natural_key else "/"
    parts = natural_key.split(sep)
    return [p.replace("-", " ") for p in parts[:-1]]


async def search_topics_trigram(
    session: AsyncSession,
    search_str: str,
    limit: int,
    min_similarity: float,
    leaf_only: bool,
    coverage_tokens: list[str] | None = None,
    min_token_coverage: float = 0.0,
) -> list[TopicTrigramHit]:
    """Match topics over their natural_key path, merging three logics:

    1. **Leaf substring (ILIKE)** — a literal match of the search string inside
       the topic's own Hindi ``display_text`` (the leaf heading). This catches
       exact occurrences (e.g. ``विभाव`` inside ``स्वभाव विभाव गुणों के लक्षण``)
       without phonetically over-matching neighbours like ``विभाग``. Crucially
       it matches the *leaf* only, **not** the ancestor path — otherwise every
       descendant of a matching ancestor (the whole ``द्रव्य/…/स्वतंत्रता``
       branch) would spuriously score 1.0. Leaf substring hits get ``sim = 1.0``.
    2. **Trigram similarity** — parent-aware fuzzy match against the full
       natural_key path (slashes → spaces), so multi-word phrase queries such as
       ``द्रव्य स्वतंत्रता`` still resolve ``द्रव्य/स्वतंत्रता/लक्षण`` even when
       no exact leaf substring is present. These contextual matches score below
       1.0 and rank under the direct leaf matches.
    3. **Token-coverage guard** — when ``coverage_tokens`` are supplied, count
       how many of the query's meaningful tokens actually appear in the
       candidate's natural_key path. Matching is **word-boundary aware**: the
       path is split into its individual Hindi words (segments) and a token
       counts only if it is a *prefix* of some segment — so ``भेद`` still matches
       the compound ``भेदाभेद`` but ``सत`` does NOT spuriously match the middle of
       ``पंचास्तिकाय`` (पंचा-स्ति-काय). Candidates below ``min_token_coverage`` are
       dropped, and coverage multiplies the score so a topic that contains *all*
       the query words outranks one sharing only an incidental token — e.g. for
       ``सत् द्रव्य भेद`` it keeps ``सत् व द्रव्य में … भेदाभेद`` above ``स्व व पर
       द्रव्य के लक्षण`` (no ``सत्``) and above ``पंचास्तिकाय`` (false ``सत्``).

    A topic qualifies if *either* of (1)/(2) matches AND it clears the coverage
    guard; the reported ``sim`` is the greater of (1)/(2). ``score`` then applies
    the leaf/container weighting and the coverage multiplier.
    """
    leaf_filter = "AND t.is_leaf = true" if leaf_only else ""

    tokens = coverage_tokens or []
    use_coverage = bool(tokens)
    params: dict = {
        "search_str": search_str,
        "like_pat": f"%{search_str}%",
        "min_similarity": min_similarity,
        "limit": limit,
    }

    if use_coverage:
        params["cov_tokens"] = tokens
        params["min_coverage"] = min_token_coverage
        params["n_tokens"] = len(tokens)
        # Bound as params (not inlined) because the char classes contain ':'
        # which would otherwise confuse SQLAlchemy's named-param parser.
        params["inword_re"] = _INWORD_STRIP_RE_SQL
        params["seg_split_re"] = _SEG_SPLIT_RE_SQL
        sql = text(f"""
            WITH ranked AS (
                SELECT
                    t.id::text AS topic_pg_id,
                    t.natural_key,
                    t.display_text,
                    t.is_leaf,
                    t.source,
                    GREATEST(
                        similarity(REPLACE(t.natural_key, '/', ' '), :search_str),
                        CASE
                            WHEN t.display_text::text ILIKE :like_pat
                            THEN 1.0 ELSE 0.0
                        END
                    ) AS sim,
                    -- natural_key split into its individual Hindi words (segments),
                    -- each normalized in-word (halant/joiners stripped) but with
                    -- word boundaries preserved so coverage matches at a word
                    -- *prefix* rather than anywhere in the collapsed path.
                    ARRAY(
                        SELECT regexp_replace(seg, :inword_re, '', 'g')
                        FROM regexp_split_to_table(lower(t.natural_key), :seg_split_re) AS seg
                        WHERE seg <> ''
                    ) AS nk_segs
                FROM topics t
                WHERE (
                    similarity(REPLACE(t.natural_key, '/', ' '), :search_str) >= :min_similarity
                    OR t.display_text::text ILIKE :like_pat
                )
                {leaf_filter}
            ),
            covered AS (
                SELECT
                    r.*,
                    (
                        SELECT count(*) FILTER (
                            WHERE EXISTS (
                                SELECT 1 FROM unnest(r.nk_segs) AS seg
                                WHERE seg LIKE tok || '%'
                            )
                        )
                        FROM unnest(CAST(:cov_tokens AS text[])) AS tok
                    )::float / :n_tokens AS coverage
                FROM ranked r
            )
            SELECT *,
                   sim
                   * CASE WHEN is_leaf THEN {LEAF_SCORE_FACTOR} ELSE {CONTAINER_SCORE_FACTOR} END
                   * coverage AS score
            FROM covered
            WHERE coverage >= :min_coverage
            ORDER BY score DESC
            LIMIT :limit
        """)
    else:
        sql = text(f"""
            WITH ranked AS (
                SELECT
                    t.id::text AS topic_pg_id,
                    t.natural_key,
                    t.display_text,
                    t.is_leaf,
                    t.source,
                    GREATEST(
                        similarity(REPLACE(t.natural_key, '/', ' '), :search_str),
                        CASE
                            WHEN t.display_text::text ILIKE :like_pat
                            THEN 1.0 ELSE 0.0
                        END
                    ) AS sim,
                    1.0 AS coverage
                FROM topics t
                WHERE (
                    similarity(REPLACE(t.natural_key, '/', ' '), :search_str) >= :min_similarity
                    OR t.display_text::text ILIKE :like_pat
                )
                {leaf_filter}
            )
            SELECT *,
                   sim * CASE WHEN is_leaf THEN {LEAF_SCORE_FACTOR} ELSE {CONTAINER_SCORE_FACTOR} END AS score
            FROM ranked
            ORDER BY score DESC
            LIMIT :limit
        """)

    rows = await session.execute(sql, params)
    hits = []
    for row in rows:
        hits.append(TopicTrigramHit(
            topic_pg_id=row.topic_pg_id,
            natural_key=row.natural_key,
            display_text=row.display_text,
            is_leaf=row.is_leaf,
            source=str(row.source),
            similarity=float(row.sim),
            token_coverage=float(row.coverage),
        ))
    logger.debug(
        "topics_match trigram search_str=%r min_sim=%.2f leaf_only=%s "
        "cov_tokens=%s min_cov=%.2f → %d hits",
        search_str, min_similarity, leaf_only, tokens, min_token_coverage, len(hits),
    )
    return hits


async def fetch_topic_extracts_batch(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, list[dict]]:
    """Fetch topic_extracts from Mongo; returns {natural_key: [{block_index, text_hi}]}.

    Delegates to common hydrate_topic_extracts_hi; strips the per-block references
    field to preserve the existing caller contract.
    """
    rich = await hydrate_topic_extracts_hi(mongo_db, natural_keys)
    return {
        nk: [
            {
                "block_index": b["block_index"],
                "text_hi": b["text_hi"],
                "main_reference": b.get("main_reference"),
            }
            for b in blocks
        ]
        for nk, blocks in rich.items()
    }


async def fetch_topic_references_batch(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, list[dict]]:
    """Fetch flattened, de-duplicated references per topic from Mongo.

    Delegates to the common ``hydrate_topic_extracts_hi`` (which already extracts
    per-block references) and flattens them per topic in document order, mirroring
    the reference-assembly logic used by ``graphrag.hydrate_topics``. Returns
    ``{natural_key: [reference_dict, ...]}``.
    """
    if not natural_keys:
        return {}
    rich = await hydrate_topic_extracts_hi(mongo_db, natural_keys)
    out: dict[str, list[dict]] = {}
    for nk, blocks in rich.items():
        seen: set[tuple] = set()
        flat_refs: list[dict] = []
        for b in blocks:
            for r in b.get("references", []):
                key = (
                    r.get("shastra_natural_key"),
                    r.get("gatha_number"),
                    r.get("teeka_natural_key"),
                    r.get("page_number"),
                )
                if key not in seen:
                    seen.add(key)
                    flat_refs.append(r)
        out[nk] = flat_refs
    return out


async def fetch_topic_source_urls(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, str]:
    """Return {natural_key: source_url} for the given topics.

    Reads the top-level ``source_url`` of each topic_extracts doc (the canonical
    jainkosh wiki page + section anchor for the extract). Topics with no doc or
    no source_url are simply absent from the result.
    """
    if not natural_keys:
        return {}
    out: dict[str, str] = {}
    cursor = mongo_db[TOPIC_EXTRACTS].find(  # type: ignore[index]
        {"natural_key": {"$in": natural_keys}},
        {"natural_key": 1, "source_url": 1, "_id": 0},
    )
    async for doc in cursor:
        url = doc.get("source_url")
        if url:
            out[doc["natural_key"]] = url
    logger.debug(
        "fetch_topic_source_urls topics=%d → urls=%d",
        len(natural_keys), len(out),
    )
    return out


async def count_topic_extract_blocks(
    mongo_db: object,
    natural_keys: list[str],
) -> dict[str, int]:
    """Return {natural_key: displayable block count} for the given topics.

    Delegates to the shared ``count_displayable_extract_blocks`` so the search
    cards count only blocks the modal would actually render (excluding
    ``see_also`` / ``table`` and text-less blocks) and gate the "पढ़ें"
    affordance accurately. Mirrors the data-service topics listing, which uses
    the same shared helper.
    """
    return await count_displayable_extract_blocks(mongo_db, natural_keys)


# Alias kept for existing callers in this module and graphrag.py
extract_references_from_blocks = extract_references
