# KairosAgent Platform

Production-hardened autonomous agent stack for DevRel + Growth operations, now with dedicated web panel.

## Stack

- Backend: FastAPI, Celery, PostgreSQL (pgvector), Redis
- LLM Router: Vertex -> OpenAI -> Gemini fallback chain
- Guardrails: QualityChecker, moderation, outbox-only external writes, runtime kill-switch
- Frontend Panel: Vite + React (matrix style Kairos chat UI)

## Repository Layout

- `api/` FastAPI endpoints (`/chat`, `/health`, webhooks, admin endpoints)
- `agents/` content/community/feedback/report agent logic
- `llm/` provider clients + router + probe
- `quality/` moderation and quality checks
- `memory/` DB schema and migrations
- `scheduler/` Celery tasks and schedules
- `tools/` X/GitHub/Hashnode/RevenueCat integrations
- `ui/kairos-rain-chat/` Kairos chat panel (React)
- `AGENT.md` agent contract and identity
- `SKILL.md` behavioral constraints and operating skill contract

## Local Run (Backend)

```bash
cp .env.example .env
# Fill your own credentials in .env

docker compose up -d postgres redis api celery-worker celery-beat
docker compose exec api python -m memory.migrations
```

Health check:

```bash
curl http://localhost:8000/health
```

## Local Run (Panel)

```bash
cd ui/kairos-rain-chat
cp .env.example .env
npm install
npm run dev
```

Panel default URL:

`http://localhost:8080`

## API Surface

- `POST /chat`
- `POST /v1/chat/completions`
- `GET /health`
- `GET /jobs/{job_id}`
- `POST /webhook/trigger-content`
- `POST /webhook/trigger-community`
- `POST /webhook/trigger-feedback`
- `POST /webhook/trigger-report`
- `POST /webhook/trigger-experiment`
- `POST /webhook/trigger-experiment-planning`
- `POST /admin/auto-mode` (`X-Admin-Token`)

## Security Rules

- `.env` is never committed.
- Do not commit tokens, secrets, bearer keys, OAuth secrets.
- Keep all external writes through outbox only.
- Use `TWITTER_EXPECTED_USERNAME` identity guard for X posting.

Quick scan before push:

```bash
git ls-files -z | xargs -0 rg -n "(sk-|ghp_|xox|AKIA|BEGIN RSA|Bearer\\s+[A-Za-z0-9._-]{12,})" || true
```

## VM Deployment (Parity with Local)

Use the same commit on VM to keep local/VM/GitHub aligned:

```bash
git pull origin main
cp .env.example .env  # only first setup
docker compose up -d --build
docker compose exec api python -m memory.migrations
```

Then start panel on VM if needed:

```bash
cd ui/kairos-rain-chat
npm install
npm run build
npm run dev -- --host 0.0.0.0 --port 8080
```

## Persistent VM Services (systemd + tunnel)

Use the bundled installer on the VM:

```bash
cd ~/revenuecat-agent
sudo bash ops/systemd/install-vm-services.sh
```

It installs and manages:

- `kairos-agent-backend.service` (docker compose backend stack)
- `kairos-agent-ui.service` (Kairos panel on port `8080`)
- `kairos-agent-tunnel.service` (cloudflared quick tunnel to panel)

Check status:

```bash
sudo systemctl status kairos-agent-backend.service
sudo systemctl status kairos-agent-ui.service
sudo systemctl status kairos-agent-tunnel.service
```

## Public Presence

- Kairos X: [@KairosAgentX](https://x.com/KairosAgentX)
- Operator X: [@AtakanElik_](https://x.com/AtakanElik_)
- Application letter: [Hashnode Post](https://revenuecat.hashnode.dev/how-agentic-ai-will-reshape-app-development-and-growth-and-why-i-m-the-right-agent-for-revenuecat)
