# API Docs

Implementation-facing index for the live API surface exposed by `services/core_service/`.

## Domains

- [Data API](./data/01_spec.md)
- [Metadata API](./metadata/01_spec.md)
- [Navigation API](./navigation/01_spec.md)

## Matching Engine Notes

The matching engine is part of the Data domain.

Relevant behaviors:

- keyword definition blocks may include `match_natural_keys`
- topic extract blocks may include `match_natural_keys`
- `GET /v1/extract-matches/{natural_key}` returns the backing match document used by the UI for deep-linking and highlighting

Detailed behavior is documented in [docs/design/matching_engine/README.md](../matching_engine/README.md).
