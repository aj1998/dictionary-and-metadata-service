# Manual Testing — `POST /v1/query/topic_neighbors`

## Basic expansion

```bash
curl -s -X POST http://localhost:8002/v1/query/topic_neighbors \
  -H 'Content-Type: application/json' \
  -d '{
    "topic_natural_keys": ["द्रव्य:द्रव्य-के-भेद-व-लक्षण"],
    "max_neighbors_per_topic": 10,
    "include_extracts": false,
    "include_references": false
  }' | python3 -m json.tool
```

Expected: `neighbors_by_anchor` with 1 entry whose `anchor_topic_natural_key` matches the input. `related_topics`, `related_keywords`, `mentioned_in_gathas` populated from Neo4j.

## Unknown anchor

```bash
curl -s -X POST http://localhost:8002/v1/query/topic_neighbors \
  -H 'Content-Type: application/json' \
  -d '{
    "topic_natural_keys": ["द्रव्य:द्रव्य-के-भेद-व-लक्षण", "does_not_exist_xyz"]
  }' | python3 -m json.tool
```

Expected: `unresolved_topic_keys: ["does_not_exist_xyz"]`, only the known anchor appears in `neighbors_by_anchor`.

## Empty anchors → 400

```bash
curl -s -X POST http://localhost:8002/v1/query/topic_neighbors \
  -H 'Content-Type: application/json' \
  -d '{"topic_natural_keys": []}' | python3 -m json.tool
```

Expected: HTTP 400 with `code: "empty_anchors"`.

## With extracts and references

```bash
curl -s -X POST http://localhost:8002/v1/query/topic_neighbors \
  -H 'Content-Type: application/json' \
  -d '{
    "topic_natural_keys": ["द्रव्य:द्रव्य-के-भेद-व-लक्षण"],
    "include_extracts": true,
    "include_references": true
  }' | python3 -m json.tool
```

Expected: each `related_topics[*].extracts_hi` has Hindi text blocks; `references` has shastra/gatha refs.

## Cap enforcement

```bash
curl -s -X POST http://localhost:8002/v1/query/topic_neighbors \
  -H 'Content-Type: application/json' \
  -d '{
    "topic_natural_keys": ["आत्मा"],
    "max_neighbors_per_topic": 2
  }' | python3 -m json.tool | python3 -c "
import json, sys
d = json.load(sys.stdin)
for g in d['neighbors_by_anchor']:
    print('related_topics:', len(g['related_topics']), '<= 2?', len(g['related_topics']) <= 2)
    print('related_keywords:', len(g['related_keywords']), '<= 2?', len(g['related_keywords']) <= 2)
    print('mentioned_in_gathas:', len(g['mentioned_in_gathas']), '<= 2?', len(g['mentioned_in_gathas']) <= 2)
"
```

Expected: each bucket has at most 2 entries.

## OpenAPI

Visit `http://localhost:8002/docs` → find `POST /v1/query/topic_neighbors` — verify request/response schema rendered.

---

## max_hops content-gated BFS (query_engine/08 Part B)

`max_hops` counts only arrivals at content-bearing (hydrated) topics. Content-less
topics are free passthroughs; keywords/gathas are terminal. Each related topic
carries `hops` and `extract_count` (sourced from the Part D node prop).

```bash
curl -s -X POST http://localhost:8002/v1/query/topic_neighbors \
  -H 'Content-Type: application/json' \
  -d '{"topic_natural_keys":["<anchor nk>"],"max_hops":2,"include_extracts":true,"include_references":true}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for g in d['neighbors_by_anchor']:
    print(g['anchor_natural_key'])
    for t in g['related_topics']:
        print('  hops=%d extract_count=%d %s' % (t['hops'], t.get('extract_count',0), t['topic_natural_key']))
"
```

Expected: topics reached through a content-less container appear at `hops=1`
(passthrough did not consume a hop); genuine 2-content-hop topics appear at
`hops=2`; `max_hops=1` excludes the hop-2 topics. No topic appears as its own
neighbour (forward-only BFS).
