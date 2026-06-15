# Phase 1 — Backend (Metadata API)

Parent: [00_overview.md](./00_overview.md)

## Goals

1. Extend `shastra.json` schema with `pdf_page_offset` + optional `pustak_offsets`.
2. Add `ORIGINAL_SHASTRA_PDF_DIR` env var read by the metadata service.
3. Add a file-streaming endpoint that returns the PDF for `(shastra_nk, pustak?)`.
4. Extend the existing shastra entity-detail payload to include the new offset fields so the frontend can compute the page number and build the brown-link URL without an extra round-trip.

No DB schema changes. No auth changes.

---

## 1. Config schema additions

File: [`parser_configs/_manual_configs/shastra.json`](../../../../parser_configs/_manual_configs/shastra.json)

Add the following optional fields to each shastra entry (do **not** touch `public_url` — it stays as the user's reference field):

```jsonc
{
  "shastra_name": "धवला",
  // ... existing fields ...
  "pdf_page_offset": 0,                  // Optional. int OR [[upToPublishedPage, offset], ...]. Default 0 when absent.
  "pustak_offsets": {                    // Optional. Only for multi-volume shastras.
    "1": 0,
    "2": -2,
    "3": 5,
    "13": [[204, 26], [215, 27]]         // Piecewise: pages <= 204 use offset 26; <= 215 use 27; ...
  }
}
```

Rules:
- `pdf_page_offset`: either an integer (can be negative) OR a list of `[upToPublishedPage, offset]` pairs. Used when `pustak` is absent or no override matches.
- `pustak_offsets`: object keyed by the **string form of the pustak value** (matches how `pustak` appears in `resolved_fields`). Each value follows the same shape as `pdf_page_offset` (scalar OR piecewise list). If a key is present, it wins over `pdf_page_offset`.
- Piecewise resolution: pairs are sorted by `upToPublishedPage` ascending; for a given published page P, the first pair where `P <= upToPublishedPage` wins. Pages beyond the last threshold inherit the last bucket's offset.
- Both fields are optional. A missing field means "offset = 0".

**Do not bulk-fill** for existing entries — the user will fill these as they download each PDF.

---

## 2. Env var

Add `ORIGINAL_SHASTRA_PDF_DIR` to `services/core_service/config.py` (the settings module already loads env vars; follow the existing pattern). Default: `None`.

When unset, the new file endpoint returns `503` for every request.

Document the new env var in the metadata domain's spec / README the same way other env vars are documented in [`docs/design/api/metadata/01_spec.md`](../../api/metadata/01_spec.md).

---

## 3. New endpoint: stream the PDF

**Route:** `GET /metadata/shastras/{shastra_nk}/pdf-file`

**Query params:**
- `pustak` (optional string). When present, the response streams `<dir>/<shastra_name>_<pustak>.pdf`; otherwise `<dir>/<shastra_name>.pdf`.

**Path resolution:**
- `<shastra_name>` is the natural key (`shastra_nk`) URL-decoded and NFC-normalized. Filenames on disk are expected NFC-normalized.
- Reject path traversal: reject any `shastra_nk` containing `/`, `\`, or `..`; reject any `pustak` containing the same.
- Build the final path via `Path(dir) / filename`; verify the resolved path is still inside `Path(dir).resolve()` (defence-in-depth against symlink escapes).

**Responses:**
- `200 application/pdf` — streaming `FileResponse` (or equivalent). Set `Content-Disposition: inline; filename="<name>.pdf"` so the browser renders rather than downloads. Set `Accept-Ranges: bytes` (so `#page=N` works with the native PDF viewer that does range requests).
- `404` — when the resolved file does not exist.
- `503` — when `ORIGINAL_SHASTRA_PDF_DIR` is unset.
- `400` — invalid `shastra_nk` / `pustak` (traversal characters).

**Logging:** log `INFO` on hit (`shastra_nk`, `pustak`, file size), `WARNING` on 404 (with the resolved absolute path so the user can debug missing files), `ERROR` on traversal attempts.

---

## 4. Extend shastra entity-detail payload

The metadata domain already exposes shastra entity-detail (used by `getEntityDetail('shastra', nk)` from the UI). Extend the response payload with:

```jsonc
{
  // ... existing fields ...
  "pdf_page_offset": 0,                   // int | [[upToPublishedPage, offset], ...], defaults to 0 if absent
  "pustak_offsets": { "1": 0, "2": -2, "13": [[204, 26], [215, 27]] }   // object<str, OffsetSpec> | null
}
```

These are read directly from the manual config loader. Add a small loader helper if not already present; cache the parsed JSON in-process (it's already manual config and read elsewhere — follow the existing pattern).

The frontend will:
- compute `pdf_page = published_page + (pustak_offsets[pustak] ?? pdf_page_offset)`
- build the link `/<api-prefix>/metadata/shastras/<nk>/pdf-file?pustak=<pustak>#page=<pdf_page>` (with `pustak=` omitted when not applicable).

---

## 5. Tests

Add the following tests (placement: alongside the existing metadata-domain tests):

1. **Config parsing**
   - Loader returns `0` when neither field is present.
   - Loader returns explicit `pdf_page_offset` when only that is present.
   - Loader returns full `pustak_offsets` dict when present.

2. **Path resolution / safety**
   - `pustak=null` → expects `<shastra_name>.pdf`.
   - `pustak="1"` → expects `<shastra_name>_1.pdf`.
   - Reject `shastra_nk` containing `..` → 400.
   - Reject `pustak` containing `/` → 400.

3. **Endpoint integration** (using a tmp dir set as `ORIGINAL_SHASTRA_PDF_DIR`)
   - Place a fake `<shastra_name>.pdf` (a few bytes are fine, content unchecked). Assert 200, `content-type: application/pdf`, `accept-ranges: bytes`.
   - Missing file → 404.
   - Env var unset → 503.

4. **Entity-detail extension**
   - Shastra with offset fields in config → response includes them.
   - Shastra without offset fields → response includes `pdf_page_offset: 0`, `pustak_offsets: null` (or omitted, document the choice).

Follow project conventions: failing test first, then implementation, then green.

---

## 6. Manual verification

```bash
# 1. Set env var
export ORIGINAL_SHASTRA_PDF_DIR=/tmp/shastras
mkdir -p "$ORIGINAL_SHASTRA_PDF_DIR"
cp /path/to/some-test.pdf "$ORIGINAL_SHASTRA_PDF_DIR/धवला_1.pdf"

# 2. Start the core service as usual; then:
curl -I "http://localhost:8001/metadata/shastras/<url-encoded-nk>/pdf-file?pustak=1"
# Expect: 200, content-type: application/pdf, accept-ranges: bytes

# 3. Hit a missing one:
curl -I "http://localhost:8001/metadata/shastras/<url-encoded-nk>/pdf-file"
# Expect: 404

# 4. Confirm offset surface in detail payload:
curl -s "http://localhost:8001/metadata/shastras/<url-encoded-nk>" | jq '{pdf_page_offset, pustak_offsets}'
```

---

## 7. Out of scope (do not implement here)

- Pre-scanning the PDF directory for availability. (We chose "always show, error on click.")
- PDF viewer route.
- Any frontend changes — see [02_phase_frontend.md](./02_phase_frontend.md).
