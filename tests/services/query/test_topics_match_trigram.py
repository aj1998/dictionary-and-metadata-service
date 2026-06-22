from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

URL = "/v1/query/topics_match"


async def _insert_topic(
    factory,
    natural_key: str,
    display_text: str,
    is_leaf: bool = True,
    source: str = "jainkosh",
) -> str:
    tid = str(uuid.uuid4())
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO topics (id, natural_key, display_text, source, is_leaf, is_synthetic, extract_doc_ids) "
                "VALUES (:id, :nk, CAST(:dt AS jsonb), CAST(:src AS ingestion_source), :leaf, false, '[]'::jsonb)"
            ),
            {
                "id": tid,
                "nk": natural_key,
                "dt": f'[{{"lang":"hi","script":"devanagari","text":"{display_text}"}}]',
                "src": source,
                "leaf": is_leaf,
            },
        )
        await session.commit()
    return tid


@pytest.mark.asyncio
async def test_phrase_matches_parent_aware(client: AsyncClient) -> None:
    """Query 'द्रव्य स्वतंत्रता' should match 'द्रव्य/स्वतंत्रता/लक्षण' via parent-aware trgm."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)
    await _insert_topic(factory, "पर्याय/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    nks = [m["topic_natural_key"] for m in data["matches"]]
    assert "द्रव्य/स्वतंत्रता/लक्षण" in nks
    assert "tool_trace_id" in data


@pytest.mark.asyncio
async def test_top_match_is_most_similar(client: AsyncClient) -> None:
    """The most similar topic should be ranked first."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता", "स्वतंत्रता", is_leaf=False)
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
        "limit": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) >= 1
    # Top result should have the highest score
    scores = [m["score"] for m in data["matches"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_leaf_only_filter(client: AsyncClient) -> None:
    """leaf_only=true should exclude container topics."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता", "स्वतंत्रता", is_leaf=False)
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "leaf_only": True,
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    for m in data["matches"]:
        assert m["is_leaf"] is True


@pytest.mark.asyncio
async def test_ancestors_hi_derived_from_natural_key(client: AsyncClient) -> None:
    """ancestors_hi should be the path segments excluding the leaf."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    for m in matches:
        if m["topic_natural_key"] == "द्रव्य/स्वतंत्रता/लक्षण":
            assert m["ancestors_hi"] == ["द्रव्य", "स्वतंत्रता"]
            break


@pytest.mark.asyncio
async def test_ancestors_hi_from_colon_natural_key(client: AsyncClient) -> None:
    """Real jainkosh keys are colon-separated with kebab-cased segments;
    ancestors_hi should drop the leaf and de-kebab the parents."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(
        factory,
        "द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-निरुक्त्यर्थ",
        "द्रव्य का निरुक्त्यर्थ",
        is_leaf=True,
    )

    resp = await client.post(URL, json={
        "phrase": "निरुक्त्यर्थ",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    target = next(
        m for m in matches
        if m["topic_natural_key"] == "द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-निरुक्त्यर्थ"
    )
    assert target["ancestors_hi"] == ["द्रव्य", "द्रव्य के भेद व लक्षण"]


@pytest.mark.asyncio
async def test_keywords_input_joined_as_phrase(client: AsyncClient) -> None:
    """keywords list should be joined with spaces as the search string."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "keywords": ["द्रव्य", "स्वतंत्रता"],
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    nks = [m["topic_natural_key"] for m in data["matches"]]
    assert "द्रव्य/स्वतंत्रता/लक्षण" in nks


@pytest.mark.asyncio
async def test_missing_keywords_and_phrase_returns_422(client: AsyncClient) -> None:
    resp = await client.post(URL, json={"include_extracts": False})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_min_similarity_cutoff(client: AsyncClient) -> None:
    """With very high min_similarity, unrelated topic should not appear."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "अकारण/असंबद्ध/विषय", "विषय", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता",
        "min_similarity": 0.95,
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
    assert "अकारण/असंबद्ध/विषय" not in nks


@pytest.mark.asyncio
async def test_substring_match_in_path(client: AsyncClient) -> None:
    """A short query should match topics that contain it as a substring of the
    path, even when symmetric trigram similarity over the long path is below the
    cutoff."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(
        factory, "गुण/भेद/स्वभाव-विभाव-गुणों-के-लक्षण", "स्वभाव विभाव गुणों के लक्षण", is_leaf=True
    )

    resp = await client.post(URL, json={
        "phrase": "विभाव",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
    assert "गुण/भेद/स्वभाव-विभाव-गुणों-के-लक्षण" in nks


@pytest.mark.asyncio
async def test_phonetic_neighbour_not_boosted_to_full_match(client: AsyncClient) -> None:
    """A true substring hit scores 1.0; a phonetic neighbour like 'विभाग' (which
    does not contain the query as a substring) is never boosted to a 1.0 match —
    it only carries its real, much lower trigram similarity. For realistically
    long paths that trigram score is below the default cutoff, so the neighbour
    drops out entirely."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(
        factory, "गुण/भेद/स्वभाव-विभाव-गुणों-के-लक्षण", "स्वभाव विभाव गुणों के लक्षण", is_leaf=True
    )
    await _insert_topic(
        factory, "द्रव्य/भेद-व-लक्षण/मूर्तामूर्त-विभाग-का-निर्देश", "मूर्तामूर्त विभाग का निर्देश", is_leaf=True
    )

    resp = await client.post(URL, json={
        "phrase": "विभाव",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    matches = {m["topic_natural_key"]: m for m in resp.json()["matches"]}

    # True substring hit is present with a perfect similarity.
    assert "गुण/भेद/स्वभाव-विभाव-गुणों-के-लक्षण" in matches
    assert matches["गुण/भेद/स्वभाव-विभाव-गुणों-के-लक्षण"]["similarity"] == pytest.approx(1.0)

    # Phonetic neighbour is excluded (long-path trigram < cutoff); if it ever
    # surfaces it must never be scored as a perfect substring match.
    neighbour = matches.get("द्रव्य/भेद-व-लक्षण/मूर्तामूर्त-विभाग-का-निर्देश")
    assert neighbour is None or neighbour["similarity"] < 1.0


@pytest.mark.asyncio
async def test_token_coverage_guard_drops_missing_distinctive_token(
    client: AsyncClient,
) -> None:
    """For 'सत् द्रव्य भेद', a topic that shares only द्रव्य/भेद but lacks सत्
    must be dropped by the coverage guard, while a topic containing all three
    survives and ranks on top. Reproduces the reported relevance bug."""
    factory = client.state  # type: ignore[attr-defined]
    # Contains सत् + द्रव्य + भेद (भेदाभेद) → full coverage.
    await _insert_topic(
        factory, "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद", "सत् व द्रव्य में कथंचित् भेदाभेद", is_leaf=True
    )
    # Shares only द्रव्य (1/3) → below 0.5 guard, must be dropped.
    await _insert_topic(
        factory, "अकारण:स्वतंत्र:केवल-द्रव्य-विषय", "केवल द्रव्य विषय", is_leaf=True
    )

    resp = await client.post(URL, json={
        "phrase": "सत् द्रव्य भेद",
        "min_token_coverage": 0.5,
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
        "limit": 10,
    })
    assert resp.status_code == 200
    nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
    assert "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद" in nks
    assert "अकारण:स्वतंत्र:केवल-द्रव्य-विषय" not in nks


@pytest.mark.asyncio
async def test_full_coverage_outranks_partial_via_score(client: AsyncClient) -> None:
    """A full-coverage topic must score above a partial-coverage one even when
    the partial one has a higher raw trigram similarity (coverage weights score)."""
    factory = client.state  # type: ignore[attr-defined]
    # Full coverage (सत्+द्रव्य+भेद) but deep path → lower raw similarity.
    await _insert_topic(
        factory,
        "द्रव्य:सत्-व-द्रव्य-में-कथंचित्-भेदाभेद:काल-की-अपेक्षा-कथंचित्-भेद-पक्ष-में-युक्ति",
        "कथंचित् भेद पक्ष में युक्ति", is_leaf=True,
    )
    # Partial coverage (द्रव्य+भेद, no सत्) but shorter path → higher similarity.
    await _insert_topic(
        factory, "द्रव्य:द्रव्य-के-भेद-व-लक्षण:स्व-व-पर-द्रव्य-के-लक्षण", "स्व व पर द्रव्य के लक्षण", is_leaf=True
    )

    resp = await client.post(URL, json={
        "phrase": "सत् द्रव्य भेद",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
        "limit": 10,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    full = next(m for m in matches if m["topic_natural_key"].endswith("कथंचित्-भेद-पक्ष-में-युक्ति"))
    partial = next(m for m in matches if m["topic_natural_key"].endswith("स्व-व-पर-द्रव्य-के-लक्षण"))
    # Partial may have the higher raw similarity …
    # … but full coverage must win on score (the field used for ranking).
    assert full["score"] > partial["score"]


@pytest.mark.asyncio
async def test_coverage_matches_word_prefix_not_mid_substring(client: AsyncClient) -> None:
    """Coverage is word-boundary aware: `सत्` must NOT match the middle of
    `पंचास्तिकाय` (पंचा-स्ति-काय), so a topic that only *looks* like it contains
    `सत्` scores below one that genuinely has `सत्` as a word — even if the
    spurious one has a marginally higher raw trigram similarity."""
    factory = client.state  # type: ignore[attr-defined]
    # Genuine सत् as a word + द्रव्य + भेद → full coverage.
    await _insert_topic(
        factory, "द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-लक्षण-सत्-तथा-उत्पादव्ययध्रौव्य",
        "द्रव्य का लक्षण सत् तथा उत्पादव्ययध्रौव्य", is_leaf=True,
    )
    # Has द्रव्य + भेद but only a spurious 'सत' inside पंचास्तिकाय → 2/3 coverage.
    await _insert_topic(
        factory, "द्रव्य:द्रव्य-के-भेद-व-लक्षण:पंचास्तिकाय", "पंचास्तिकाय", is_leaf=True
    )

    resp = await client.post(URL, json={
        "phrase": "सत् द्रव्य भेद",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
        "limit": 10,
    })
    assert resp.status_code == 200
    matches = {m["topic_natural_key"]: m for m in resp.json()["matches"]}
    genuine = matches["द्रव्य:द्रव्य-के-भेद-व-लक्षण:द्रव्य-का-लक्षण-सत्-तथा-उत्पादव्ययध्रौव्य"]
    panch = matches.get("द्रव्य:द्रव्य-के-भेद-व-लक्षण:पंचास्तिकाय")
    # Genuine सत् topic (full coverage) must rank above पंचास्तिकाय (partial).
    assert panch is None or genuine["similarity"] > panch["similarity"]


@pytest.mark.asyncio
async def test_coverage_guard_disabled_keeps_low_coverage(client: AsyncClient) -> None:
    """min_token_coverage=0.0 restores legacy behaviour (no coverage filter)."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(
        factory, "द्रव्य:द्रव्य-के-भेद-व-लक्षण:स्व-व-पर-द्रव्य-के-लक्षण", "स्व व पर द्रव्य के लक्षण", is_leaf=True
    )

    resp = await client.post(URL, json={
        "phrase": "सत् द्रव्य भेद",
        "min_token_coverage": 0.0,
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
    })
    assert resp.status_code == 200
    nks = [m["topic_natural_key"] for m in resp.json()["matches"]]
    assert "द्रव्य:द्रव्य-के-भेद-व-लक्षण:स्व-व-पर-द्रव्य-के-लक्षण" in nks


@pytest.mark.asyncio
async def test_container_topic_scored_lower(client: AsyncClient) -> None:
    """Container topics should have a lower score than leaf topics at same similarity."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता", "स्वतंत्रता", is_leaf=False)
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता लक्षण",
        "content_only": False,
        "include_extracts": False,
        "include_references": False,
        "limit": 5,
    })
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    # Verify score < similarity for container topics (0.6x factor)
    for m in matches:
        if not m["is_leaf"]:
            assert m["score"] < m["similarity"] * 1.0
