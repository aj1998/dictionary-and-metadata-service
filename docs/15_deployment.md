# 15 — Deployment

Single-host Docker Compose deployment, vertical-scale only. Designed so any single service can be split off later by swapping the `services:` entry for an external host.

## Topology

```
                     ┌────────────────┐
                     │     nginx      │   :80, :443
                     └─┬──────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
    Next.js         metadata-svc   dictionary-svc       query-svc
     :3000           :8001          :8002                :8003
        │              │              │                    │
        └────────┬─────┴───────┬──────┴────────┬──────────┘
                 │             │               │
                 ▼             ▼               ▼
            Postgres :5432  Mongo :27017   Neo4j :7687
                 ▲             ▲               ▲
                 └─────┬───────┴───────┬───────┘
                       │               │
                       ▼               ▼
                  Celery worker   Celery beat
                       │
                       ▼
                  Redis :6379
```

## `docker-compose.yml`

```yaml
version: "3.9"

x-env-files: &env_files
  - ./.env
  - ./.env.local

services:
  nginx:
    image: nginx:1.27-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./deploy/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/.htpasswd:/etc/nginx/.htpasswd:ro
      - ./deploy/certs:/etc/nginx/certs:ro
    depends_on: [ui, metadata-service, dictionary-service, query-service]

  ui:
    build: ./ui
    env_file: *env_files
    environment:
      NEXT_PUBLIC_BASE_URL: ${PUBLIC_BASE_URL}
      METADATA_SERVICE_URL: http://metadata-service:8001
      DICTIONARY_SERVICE_URL: http://dictionary-service:8002
      QUERY_SERVICE_URL: http://query-service:8003
    depends_on: [metadata-service, dictionary-service, query-service]

  metadata-service:
    build: { context: ., dockerfile: services/metadata_service/Dockerfile }
    env_file: *env_files
    depends_on: [postgres]
    healthcheck: &fastapi_healthcheck
      test: ["CMD", "curl", "-fsS", "http://localhost:${PORT:-8001}/healthz"]
      interval: 10s
      timeout: 3s
      retries: 5

  dictionary-service:
    build: { context: ., dockerfile: services/dictionary_service/Dockerfile }
    env_file: *env_files
    depends_on: [postgres, mongo, neo4j]
    healthcheck: *fastapi_healthcheck

  query-service:
    build: { context: ., dockerfile: services/query_service/Dockerfile }
    env_file: *env_files
    depends_on: [postgres, mongo, neo4j]
    healthcheck: *fastapi_healthcheck

  celery-worker:
    build: { context: ., dockerfile: workers/Dockerfile }
    command: celery -A workers.app worker -l info -Q default,ingestion,enrichment
    env_file: *env_files
    depends_on: [postgres, mongo, neo4j, redis]
    volumes:
      - ./data/raw:/app/data/raw
      - ${NIKKYJAIN_LOCAL_PATH}:/app/external/nikkyjain:ro
      - ./vyakaran_vishleshan:/app/vyakaran_vishleshan:ro

  celery-beat:
    build: { context: ., dockerfile: workers/Dockerfile }
    command: celery -A workers.app beat -l info
    env_file: *env_files
    depends_on: [redis, postgres]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: jain_kb
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./deploy/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d jain_kb"]
      interval: 10s
      timeout: 3s
      retries: 5

  mongo:
    image: mongo:7
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
      MONGO_INITDB_DATABASE: jain_kb
    volumes:
      - mongo_data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 3s
      retries: 5

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: ${NEO4J_USER}/${NEO4J_PASSWORD}
      NEO4J_server_memory_heap_initial__size: 1g
      NEO4J_server_memory_heap_max__size: 2g
      NEO4J_db_tx__timeout: 30s
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_plugins:/plugins
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u $$NEO4J_USER -p $$NEO4J_PASSWORD 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

volumes:
  postgres_data:
  mongo_data:
  neo4j_data:
  neo4j_logs:
  neo4j_plugins:
  redis_data:
```

## `.env` (template)

```
# DB credentials
POSTGRES_USER=jainkb
POSTGRES_PASSWORD=change-me
MONGO_USER=jainkb
MONGO_PASSWORD=change-me
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-me

# Connection strings (same DSNs across all backend services)
POSTGRES_DSN=postgresql+asyncpg://jainkb:change-me@postgres:5432/jain_kb
MONGO_URI=mongodb://jainkb:change-me@mongo:27017/jain_kb?authSource=admin
NEO4J_URI=bolt://neo4j:7687
NEO4J_DATABASE=jainkb
REDIS_URL=redis://redis:6379/0

# Cataloguesearch-chat read-replica (FQ4)
CHAT_DB_DSN=postgresql://reader:reader@chat-db:5432/chat
CHAT_VIEW_NAME=chat_topic_candidates_v1

# Ingestion
NIKKYJAIN_LOCAL_PATH=/Users/anubhavjain/Coding/Jinvani/nikkyjain-clone
RAW_HTML_DIR=/app/data/raw
JAINKOSH_RPS=1
PULLER_LOOKBACK_DAYS=14

# Public URL
PUBLIC_BASE_URL=https://kb.example.org

# API keys
QUERY_SERVICE_API_KEY=change-me-32+chars
```

## `nginx.conf` (excerpt)

```
events {}
http {
  upstream ui            { server ui:3000; }
  upstream metadata_svc  { server metadata-service:8001; }
  upstream dictionary_svc{ server dictionary-service:8002; }
  upstream query_svc     { server query-service:8003; }

  server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
  }

  server {
    listen 443 ssl http2;
    server_name kb.example.org;
    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    # Public UI
    location / { proxy_pass http://ui; proxy_set_header Host $host; }

    # Public APIs (read-only GETs only)
    location /v1/keywords      { proxy_pass http://dictionary_svc; }
    location /v1/topics        { proxy_pass http://dictionary_svc; }
    location /v1/gathas        { proxy_pass http://dictionary_svc; }
    location /v1/browse        { proxy_pass http://dictionary_svc; }
    location /v1/search        { proxy_pass http://dictionary_svc; }
    location /v1/shastras      { proxy_pass http://metadata_svc; }
    location /v1/authors       { proxy_pass http://metadata_svc; }
    location /v1/teekas        { proxy_pass http://metadata_svc; }
    location /v1/books         { proxy_pass http://metadata_svc; }
    location /v1/pravachans    { proxy_pass http://metadata_svc; }
    location /v1/anuyogas      { proxy_pass http://metadata_svc; }
    location /v1/graphrag      { proxy_pass http://query_svc; }

    # Admin (auth + IP allowlist)
    location /admin/ {
      auth_basic "Restricted";
      auth_basic_user_file /etc/nginx/.htpasswd;
      allow 192.168.0.0/16; allow 10.0.0.0/8; deny all;
      proxy_pass http://ui;
    }
    location /v1/admin/ {
      auth_basic "Restricted";
      auth_basic_user_file /etc/nginx/.htpasswd;
      allow 192.168.0.0/16; allow 10.0.0.0/8; deny all;

      # path-based fanout
      location /v1/admin/ingest        { proxy_pass http://dictionary_svc; }
      location /v1/admin/topics        { proxy_pass http://dictionary_svc; }
      location /v1/admin/keywords      { proxy_pass http://dictionary_svc; }
      location /v1/admin/topic-candidates { proxy_pass http://dictionary_svc; }
      location /v1/admin/graph         { proxy_pass http://dictionary_svc; }
      location /v1/admin/logs          { proxy_pass http://query_svc; }
      location /v1/admin/stats         { proxy_pass http://metadata_svc; }
      location /v1/admin/              { proxy_pass http://metadata_svc; }
    }

    client_max_body_size 16m;
    gzip on;
    gzip_types text/css application/javascript application/json text/plain;
  }
}
```

## Migrations on startup

Each backend service has an `entrypoint.sh` that runs:

```bash
#!/usr/bin/env sh
set -e
alembic upgrade head    # safe to run from any service; idempotent
exec "$@"
```

Only metadata-service runs the seed migration `0002_seed_anuyogas.sql` (use the env flag `RUN_SEEDS=true`).

## Volumes & backups

| Volume | Backup target | Frequency |
|---|---|---|
| `postgres_data` | `pg_basebackup` to `/backups/pg/<date>/` | nightly @ 03:00, retain 14 |
| `mongo_data`    | `mongodump --gzip --archive=/backups/mongo/<date>.gz` | nightly @ 03:30, retain 14 |
| `neo4j_data`    | `neo4j-admin database dump jainkb` | nightly @ 04:00, retain 7 (graph is rebuildable from PG+Mongo, so smaller window) |
| `data/raw`      | `tar -czf` to `/backups/raw/<date>.tar.gz` | weekly, retain 4 |

A simple host-side cron runs the four jobs. Off-host copy via `rclone` to S3-compatible storage.

## Observability

- **Logs**: each service writes JSON logs to stdout; `docker compose logs -f` for development. In production, point Docker logging driver at Loki/Promtail.
- **Metrics**: each FastAPI service exposes `GET /metrics` (Prometheus). The shipped Compose has a `prometheus` and `grafana` service in a separate `docker-compose.observability.yml` (not detailed here; standard).
- **Errors**: optional Sentry DSN via env `SENTRY_DSN`.

## Resource sizing (single VM)

For 2,000–2,500 shastras × ~1,000 pages eventual scale (per Q1):

| Component | Initial | Year-1 estimate |
|---|---|---|
| CPU | 4 vCPU | 16 vCPU |
| RAM | 16 GB | 64 GB |
| Disk | 200 GB SSD | 1 TB SSD |
| Postgres | 4 GB heap | 16 GB heap, partition `query_logs` by month |
| Mongo | 4 GB | WiredTiger cache 16 GB |
| Neo4j | 2 GB heap | 8 GB heap, page cache 8 GB |

Vertical scale is the path — if Neo4j becomes the bottleneck, sharding the graph is **out of scope**; we'd consider read replicas (paid Enterprise) at that point.

## Definition of Done

- [ ] `docker compose up` boots all services; healthchecks pass.
- [ ] `alembic upgrade head` runs successfully on first boot, no-op on subsequent boots.
- [ ] Public UI reachable at `https://<host>/`; admin reachable at `/admin/` only with basic auth.
- [ ] Backup cron scripts exist under `deploy/backup/` and run dry-run successfully.
- [ ] Resource sizing documented in README with current and projected numbers.
- [ ] `.env.example` checked in; `.env` and `.env.local` are gitignored.
