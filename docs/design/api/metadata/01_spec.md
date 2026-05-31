# Metadata API Spec (Core Service)

> This domain is now served by [`core-service`](../refactoring/01_merge_metadata_data_navigation.md) from `services/core_service/`.
> Legacy pre-merge spec is archived at [archived/01_spec.md](./archived/01_spec.md).

## Runtime
- Service: `core-service`
- Module path: `services/core_service/`
- Port: `8001`
- Base path: `/v1`

## Metadata routes
- `GET /v1/authors`
- `GET /v1/authors/{ident}`
- `POST /v1/authors`
- `PATCH /v1/authors/{ident}`
- `GET /v1/shastras`
- `GET /v1/shastras/{ident}`
- `POST /v1/shastras`
- `PATCH /v1/shastras/{ident}`
- `GET /v1/anuyogas`
- `GET /v1/teekas`
- `GET /v1/teekas/{ident}`
- `POST /v1/teekas`
- `PATCH /v1/teekas/{ident}`
- `GET /v1/publications`
- `GET /v1/publications/{ident}`
- `POST /v1/publications`
- `PATCH /v1/publications/{ident}`
- `GET /v1/publishers`
- `GET /v1/books`
- `GET /v1/books/{ident}`
- `POST /v1/books`
- `PATCH /v1/books/{ident}`
- `GET /v1/pravachans`
- `GET /v1/pravachans/{ident}`
- `POST /v1/pravachans`
- `PATCH /v1/pravachans/{ident}`
- `GET /v1/admin/search`

## Notes
- Endpoint contracts are unchanged from the archived spec.
- Only module/layout changed from `services/metadata_service/` to `services/core_service/domains/metadata/`.
