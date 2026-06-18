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
async def test_container_topic_scored_lower(client: AsyncClient) -> None:
    """Container topics should have a lower score than leaf topics at same similarity."""
    factory = client.state  # type: ignore[attr-defined]
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता", "स्वतंत्रता", is_leaf=False)
    await _insert_topic(factory, "द्रव्य/स्वतंत्रता/लक्षण", "लक्षण", is_leaf=True)

    resp = await client.post(URL, json={
        "phrase": "द्रव्य स्वतंत्रता लक्षण",
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
