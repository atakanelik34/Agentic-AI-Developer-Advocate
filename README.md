# RevenueCat Agent v2.2

Production-hardened, vendor-agnostic autonomous agent runtime for RevenueCat advocacy workflows.

## Highlights

- Vendor-agnostic LLM router (`Vertex -> OpenAI -> Gemini` default fallback)
- Vertex model rotation: `heavy` workloads use `VERTEX_HEAVY_MODEL`, daily flows rotate across `VERTEX_FLASH_MODELS`
- AGENT/SKILL contract layer (`AGENT.md` + `SKILL.md`) with parser-backed mandatory validation
- Independent moderation pipeline (`MODERATION_PROVIDER=openai` default)
- Outbox-only external writes (no direct posting from agents)
- Quality gate with code checks, source link checks, and duplicate control
- DB-backed kill-switch (`AUTO_MODE`) with optional env override (`FORCE_AUTO_MODE`)
- Growth experiment planning/execution with automatic baseline fill
- Nightly backup + weekly restore smoke test

## Project Layout

- `agents/`: content/community/feedback/report agents
- `AGENT.md`: stable identity contract
- `SKILL.md`: task-specific execution rules
- `api/`: FastAPI webhook and observability endpoints
- `memory/`: pgvector persistence + migrations + `context_builder` + `learner`
- `llm/`: provider adapters and router
- `quality/`: moderation + quality checker
- `tools/`: platform API clients
- `scheduler/`: Celery tasks and schedules
- `ops/backup/`: backup and restore jobs
- `config/`: pricing and rate-limit policies

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- `rclone` for remote backup uploads
- On GCP VM: `aiplatform.googleapis.com` enabled
- RevenueCat v2 credentials: `REVENUECAT_API_KEY` + `REVENUECAT_PROJECT_ID` (`REVENUECAT_V1_API_KEY` optional for `/v1/subscribers` fallback)

## Quick Start

```bash
git clone <repo>
cd revenuecat-agent
cp .env.example .env
# fill .env values
docker-compose up -d

docker-compose exec api python -m memory.migrations
```

Start worker/beat if not already started by compose commands:

```bash
docker-compose exec celery-worker celery -A scheduler.tasks:celery_app worker --loglevel=INFO
docker-compose exec celery-beat celery -A scheduler.tasks:celery_app beat --loglevel=INFO
```

## API Endpoints

- `POST /webhook/trigger-content`
- `POST /webhook/trigger-community`
- `POST /webhook/trigger-feedback`
- `POST /webhook/trigger-report`
- `POST /webhook/trigger-experiment`
- `POST /chat` (direct chat)
- `POST /v1/chat/completions` (OpenAI-compatible)
- `GET /chat-ui` (browser UI)
- `GET /jobs/{job_id}`
- `GET /health`
- `GET /metrics/weekly`
- `GET /content/recent`
- `POST /admin/auto-mode` (`X-Admin-Token` required)

## Runtime Modes

1. `DRY_RUN`: no external writes, outbox events are consumed as dry-run.
2. `AUTO_LOW_RISK`: autonomous for low-risk actions.
3. `AUTO_ALL`: full automation with guardrails.

Priority order:

1. `FORCE_AUTO_MODE` env (if set)
2. `system_config.AUTO_MODE` in DB

## Vertex Rotation

- `workload=heavy`: strongest Gemini model (`VERTEX_HEAVY_MODEL`, default `gemini-2.5-pro`)
- `workload=standard`: round-robin flash models (`VERTEX_FLASH_MODELS`, default `gemini-2.5-flash,gemini-2.5-flash-lite`)
- Fallback model for unknown workload: `VERTEX_MODEL`

## Content Pipeline Order

1. Idea generation
2. Draft generation
3. Draft record insert (`status=draft`)
4. Embedding generation
5. Similarity check (90-day window)
6. Quality check
7. If pass: enqueue `publish_content` outbox event
8. Outbox publisher writes externally and marks `status=published`
9. Outbox promoter publishes thread

## Schedules (UTC)

- Tue/Thu 10:00: content pipeline
- Hourly: community monitor
- Fri 14:00: feedback collection
- Mon 09:00: weekly report
- Mon 11:00: experiment planning
- Mon 13:00: experiment execution
- Daily 02:30: backup
- Sun 03:00: restore smoke test
- Every minute: outbox dispatch

## Tests

```bash
pytest -q
```

Refresh RevenueCat v2 endpoint registry from official docs:

```bash
python scripts/sync_revenuecat_v2_registry.py
```

## Notes

- Discord integration is optional (`ENABLE_DISCORD=false` by default).
- Backups require a remote target (`BACKUP_REMOTE_URL`); local-only backup is intentionally unsupported.
- `config/rate_limits.yaml` is the source of truth for retry windows and limits.
- RevenueCat v2 endpoint registry is stored at `config/revenuecat_v2_endpoints.json` and can be called generically via `RevenueCatTool.request_v2(...)`.
