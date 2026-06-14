from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import ADMIN_AUTH

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Unit: config parsing via get_shastra_pdf_offsets
# ---------------------------------------------------------------------------

class TestShastraPdfOffsets:
    def setup_method(self):
        # Clear lru_cache between tests so mock patches take effect
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    def teardown_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    def _patch_config(self, entries):
        from services.core_service.domains.metadata.services import shastra_pdf
        return patch.object(shastra_pdf, "_load_shastra_config", return_value=entries)

    def test_no_offset_fields_returns_zero_and_none(self):
        from services.core_service.domains.metadata.services.shastra_pdf import get_shastra_pdf_offsets
        with self._patch_config([{"shastra_name": "धवला"}]):
            offset, pustak = get_shastra_pdf_offsets("धवला")
        assert offset == 0
        assert pustak is None

    def test_pdf_page_offset_only(self):
        from services.core_service.domains.metadata.services.shastra_pdf import get_shastra_pdf_offsets
        with self._patch_config([{"shastra_name": "धवला", "pdf_page_offset": 15}]):
            offset, pustak = get_shastra_pdf_offsets("धवला")
        assert offset == 15
        assert pustak is None

    def test_pustak_offsets_present(self):
        from services.core_service.domains.metadata.services.shastra_pdf import get_shastra_pdf_offsets
        config = [{"shastra_name": "धवला", "pdf_page_offset": 3, "pustak_offsets": {"1": 0, "2": -2}}]
        with self._patch_config(config):
            offset, pustak = get_shastra_pdf_offsets("धवला")
        assert offset == 3
        assert pustak == {"1": 0, "2": -2}

    def test_unknown_shastra_returns_defaults(self):
        from services.core_service.domains.metadata.services.shastra_pdf import get_shastra_pdf_offsets
        with self._patch_config([{"shastra_name": "धवला"}]):
            offset, pustak = get_shastra_pdf_offsets("unknown")
        assert offset == 0
        assert pustak is None


# ---------------------------------------------------------------------------
# Unit: path resolution
# ---------------------------------------------------------------------------

class TestResolvePdfPath:
    def setup_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    def teardown_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    def _patch_config(self, entries):
        from services.core_service.domains.metadata.services import shastra_pdf
        return patch.object(shastra_pdf, "_load_shastra_config", return_value=entries)

    def test_no_pustak_flat_path(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        with self._patch_config([{"shastra_name": "धवला"}]):
            result = resolve_pdf_path(str(tmp_path), "धवला", None)
        assert result is not None
        assert result == (tmp_path / "धवला.pdf").resolve()

    def test_pustak_flat_path(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        with self._patch_config([{"shastra_name": "धवला"}]):
            result = resolve_pdf_path(str(tmp_path), "धवला", "1")
        assert result is not None
        assert result == (tmp_path / "धवला_1.pdf").resolve()

    def test_pdf_filename_subdirectory_no_pustak(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        config = [{"shastra_name": "पंचास्तिकाय", "pdf_filename": "panchastikaya"}]
        with self._patch_config(config):
            result = resolve_pdf_path(str(tmp_path), "पंचास्तिकाय", None)
        assert result is not None
        assert result == (tmp_path / "पंचास्तिकाय" / "panchastikaya.pdf").resolve()

    def test_pdf_filename_subdirectory_with_pustak(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        config = [{"shastra_name": "धवला", "pdf_filename": "dhavala"}]
        with self._patch_config(config):
            result = resolve_pdf_path(str(tmp_path), "धवला", "2")
        assert result is not None
        assert result == (tmp_path / "धवला" / "dhavala_2.pdf").resolve()

    def test_traversal_in_shastra_nk_returns_none(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        with self._patch_config([]):
            result = resolve_pdf_path(str(tmp_path), "../etc/passwd", None)
        assert result is None

    def test_traversal_in_pustak_returns_none(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        with self._patch_config([{"shastra_name": "धवला"}]):
            result = resolve_pdf_path(str(tmp_path), "धवला", "/etc/passwd")
        assert result is None

    def test_dotdot_in_pustak_returns_none(self, tmp_path):
        from services.core_service.domains.metadata.services.shastra_pdf import resolve_pdf_path
        with self._patch_config([{"shastra_name": "धवला"}]):
            result = resolve_pdf_path(str(tmp_path), "धवला", "..")
        assert result is None


# ---------------------------------------------------------------------------
# Integration: HTTP endpoint
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def author(client: AsyncClient):
    r = await client.post(
        "/v1/admin/authors",
        json={
            "natural_key": "kundkund",
            "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्द"}],
            "kind": "acharya",
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


@pytest_asyncio.fixture
async def shastra(client: AsyncClient, author):
    r = await client.post(
        "/v1/admin/shastras",
        json={
            "natural_key": "pravachansaar",
            "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
            "author_id": author["id"],
            "anuyoga_ids": [],
        },
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201
    return r.json()


class TestShastraPdfEndpoint:
    def setup_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    def teardown_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    async def test_200_with_pdf_file(self, client: AsyncClient, tmp_path):
        pdf_file = tmp_path / "pravachansaar.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        from services.core_service.domains.metadata.services import shastra_pdf
        with (
            patch.object(shastra_pdf, "_load_shastra_config", return_value=[{"shastra_name": "pravachansaar"}]),
            patch("services.core_service.domains.metadata.routers.shastras.settings") as mock_settings,
        ):
            mock_settings.ORIGINAL_SHASTRA_PDF_DIR = str(tmp_path)
            r = await client.get("/v1/shastras/pravachansaar/pdf-file")

        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers.get("accept-ranges") == "bytes"

    async def test_404_missing_file(self, client: AsyncClient, tmp_path):
        from services.core_service.domains.metadata.services import shastra_pdf
        with (
            patch.object(shastra_pdf, "_load_shastra_config", return_value=[{"shastra_name": "pravachansaar"}]),
            patch("services.core_service.domains.metadata.routers.shastras.settings") as mock_settings,
        ):
            mock_settings.ORIGINAL_SHASTRA_PDF_DIR = str(tmp_path)
            r = await client.get("/v1/shastras/pravachansaar/pdf-file")

        assert r.status_code == 404

    async def test_503_when_dir_not_configured(self, client: AsyncClient):
        with patch("services.core_service.domains.metadata.routers.shastras.settings") as mock_settings:
            mock_settings.ORIGINAL_SHASTRA_PDF_DIR = None
            r = await client.get("/v1/shastras/pravachansaar/pdf-file")

        assert r.status_code == 503

    async def test_400_traversal_in_nk(self, client: AsyncClient, tmp_path):
        # Use '..' embedded in the nk (without a URL slash) to test traversal rejection.
        # %2F-encoded slashes are normalized by the router before reaching the handler.
        with patch("services.core_service.domains.metadata.routers.shastras.settings") as mock_settings:
            mock_settings.ORIGINAL_SHASTRA_PDF_DIR = str(tmp_path)
            r = await client.get("/v1/shastras/..evil/pdf-file")

        assert r.status_code == 400


class TestShastraDetailOffsets:
    def setup_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    def teardown_method(self):
        from services.core_service.domains.metadata.services.shastra_pdf import _load_shastra_config
        _load_shastra_config.cache_clear()

    async def test_offsets_present_in_config(self, client: AsyncClient, author, shastra):
        from services.core_service.domains.metadata.services import shastra_pdf
        config = [{"shastra_name": "pravachansaar", "pdf_page_offset": 10, "pustak_offsets": {"1": 5}}]
        with patch.object(shastra_pdf, "_load_shastra_config", return_value=config):
            r = await client.get("/v1/shastras/pravachansaar")
        assert r.status_code == 200
        data = r.json()
        assert data["pdf_page_offset"] == 10
        assert data["pustak_offsets"] == {"1": 5}

    async def test_no_offset_fields_defaults(self, client: AsyncClient, author, shastra):
        from services.core_service.domains.metadata.services import shastra_pdf
        with patch.object(shastra_pdf, "_load_shastra_config", return_value=[{"shastra_name": "other"}]):
            r = await client.get("/v1/shastras/pravachansaar")
        assert r.status_code == 200
        data = r.json()
        assert data["pdf_page_offset"] == 0
        assert data["pustak_offsets"] is None
