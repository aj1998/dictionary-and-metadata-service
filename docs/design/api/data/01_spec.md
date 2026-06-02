# Data API Spec (Core Service)

> This domain is now served by [`core-service`](../../archived/refactoring/01_merge_metadata_data_navigation.md) from `services/core_service/`.
> Legacy pre-merge spec is archived at [archived/01_spec.md](./archived/01_spec.md).

## Runtime
- Service: `core-service`
- Module path: `services/core_service/`
- Port: `8001`
- Base path: `/v1`

## Data routes
- `GET /v1/keywords`
- `GET /v1/keywords/letters`
- `GET /v1/keywords/{ident}`
- `PATCH /v1/admin/keywords/{ident}`
- `GET /v1/topics`
- `GET /v1/topics/{ident}`
- `GET /v1/gathas`
- `GET /v1/gathas/{ident}`
- `GET /v1/kalashas`
- `GET /v1/kalashas/{ident}`
- `GET /v1/browse/letters`
- `GET /v1/browse/{entity}`
- `GET /v1/search`
- `GET /v1/stats`

## Notes
- Endpoint contracts are unchanged from the archived spec.
- Only module/layout changed from `services/data_service/` to `services/core_service/domains/data/`.
