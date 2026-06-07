# Navigation API Spec (Core Service)

> This domain is now served by [`core-service`](../../archived/refactoring/01_merge_metadata_data_navigation.md) from `services/core_service/`.
> Legacy pre-merge spec is archived at [archived/01_spec.md](./archived/01_spec.md).

## Runtime
- Service: `core-service`
- Module path: `services/core_service/`
- Port: `8001`
- Base path: `/v1`

## Navigation routes
- `GET /v1/keywords/{token}/resolve`
- `GET /v1/keywords/{nk}/topics`
- `GET /v1/topics/{nk}/neighbors`
- `GET /v1/topics/{nk}/keywords`
- `GET /v1/topics/{nk}/ancestors` — returns `{topic_natural_key, parent_keyword_natural_key, ancestors[]}`. `ancestors` is the ordered chain of topic natural_keys walked via `PART_OF` outbound from the topic to its root (root first → direct parent last; topic itself excluded). Used by the UI `TopicTreeBrowser` to auto-expand columns to a target topic referenced via `?topic=` on the dictionary keyword page.
- `GET /v1/topics/{nk}/related` — returns `{topic_natural_key, related: [{natural_key, display_text, label, is_stub}, ...]}`. Walks `RELATED_TO` edges from the topic and returns both `Topic` and `Keyword` targets (label = `"Topic"` or `"Keyword"`). Stubs included by default; pass `?exclude_stubs=true` to filter. Powers the "संबंधित विषय" expansion on label-seed rows in the UI (label-seed see_also targets are frequently stub keywords like `वस्तु`, which `/neighbors` cannot return because its `RELATED_TO` clause is restricted to `Topic` targets).
- `GET /v1/graph/shortest_path`
- `GET /v1/landing`
- `GET /v1/landing/random`
- `GET /v1/expand/{nk}`
- `GET /v1/preview/{nk}`
- `POST /v1/admin/keywords/{id}/aliases`
- `POST /v1/admin/topics/{nk}/edges`
- `POST /v1/admin/graph/resync`
- `GET /v1/admin/graph/stubs`

## Notes
- Endpoint contracts are unchanged from the archived spec.
- Only module/layout changed from `services/navigation_service/` to `services/core_service/domains/navigation/`.
