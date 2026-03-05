"""FastAPI app for webhook triggers and monitoring endpoints."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID
from uuid import uuid4

import redis
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.logging import configure_logging
from core.settings import get_settings
from memory.store import MemoryStore
from ops.system_config import SystemConfigService
from runtime import build_runtime
from scheduler.tasks import (
    run_community_monitor,
    run_content_pipeline,
    run_feedback_collection,
    run_growth_experiment_execution,
    run_growth_experiment_planning,
    run_weekly_report,
)


settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title="RevenueCat Agent API", version="2.2.0")
CHAT_UI_FILE = Path(__file__).with_name("chat_ui.html")

allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _enforce_agent_identity(reply_text: str) -> str:
    """Normalize legacy aliases in interactive chat responses."""

    expected = settings.agent_name.strip() or "KairosAgent"
    sanitized = reply_text
    for alias in ("RevenueCatAgent", "RevenueCat Agent"):
        sanitized = sanitized.replace(alias, expected)
    return sanitized


class TriggerContentRequest(BaseModel):
    """Manual trigger payload for content pipeline."""

    force: bool = False
    campaign_id: str | None = None


class TriggerCommunityRequest(BaseModel):
    """Manual trigger payload for community monitoring."""

    limit: int = Field(default=50, ge=1, le=500)


class TriggerReportRequest(BaseModel):
    """Manual trigger payload for weekly report generation."""

    week_start: date | None = None


class TriggerExperimentRequest(BaseModel):
    """Manual trigger payload for experiment execution."""

    experiment_id: str | None = None


class AutoModeRequest(BaseModel):
    """Admin payload for runtime auto mode switch."""

    mode: Literal["DRY_RUN", "AUTO_LOW_RISK", "AUTO_ALL"]


class ChatTurn(BaseModel):
    """Single conversational turn."""

    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """Interactive chat payload."""

    message: str = Field(min_length=1, max_length=12000)
    history: list[ChatTurn] = Field(default_factory=list)
    workload: Literal["standard", "heavy"] = "standard"


class ChatResponse(BaseModel):
    """Interactive chat response."""

    reply: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class OpenAIChatMessage(BaseModel):
    """OpenAI-compatible chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class OpenAIChatRequest(BaseModel):
    """Minimal OpenAI-compatible chat completions request."""

    model: str | None = None
    messages: list[OpenAIChatMessage]
    stream: bool = False
    workload: Literal["standard", "heavy"] | None = None


def get_store() -> MemoryStore:
    """Return shared DB store object."""

    return MemoryStore()


@lru_cache(maxsize=1)
def get_runtime() -> dict[str, object]:
    """Cache runtime container for interactive chat endpoints."""

    return build_runtime()


def _chat_generate(message: str, history: list[ChatTurn], workload: str) -> ChatResponse:
    runtime = get_runtime()
    content_agent = runtime["agents"]["content"]  # type: ignore[index]

    safe_history = [
        {"role": turn.role, "content": turn.content[:2500]}
        for turn in history[-12:]
    ]
    user_payload = json.dumps(
        {
            "type": "interactive_chat",
            "history": safe_history,
            "message": message,
            "instructions": (
                "Answer directly and practically. If a request maps to one of the system endpoints, "
                "suggest the exact endpoint and payload."
            ),
        },
        ensure_ascii=True,
    )

    response = content_agent.router.generate(  # type: ignore[attr-defined]
        system_prompt=content_agent.build_system_prompt(),  # type: ignore[attr-defined]
        user_prompt=user_payload,
        workload=workload,
    )
    return ChatResponse(
        reply=_enforce_agent_identity(response.text.strip()),
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


def verify_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    """Validate internal admin token for protected endpoints."""

    if not settings.admin_api_token:
        raise HTTPException(status_code=503, detail="admin token not configured")
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=401, detail="invalid admin token")


@app.post("/webhook/trigger-content")
def trigger_content(payload: TriggerContentRequest, store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Trigger content pipeline asynchronously."""

    job_id = store.create_job_run("content_pipeline", {"force": payload.force, "campaign_id": payload.campaign_id})
    run_content_pipeline.delay(force=payload.force, campaign_id=payload.campaign_id, job_run_id=str(job_id))
    return {"job_id": str(job_id)}


@app.post("/webhook/trigger-community")
def trigger_community(payload: TriggerCommunityRequest, store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Trigger community scan asynchronously."""

    job_id = store.create_job_run("community_monitor", {"limit": payload.limit})
    run_community_monitor.delay(limit=payload.limit, job_run_id=str(job_id))
    return {"job_id": str(job_id)}


@app.post("/webhook/trigger-feedback")
def trigger_feedback(store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Trigger feedback collection asynchronously."""

    job_id = store.create_job_run("feedback_collection", {})
    run_feedback_collection.delay(job_run_id=str(job_id))
    return {"job_id": str(job_id)}


@app.post("/webhook/trigger-report")
def trigger_report(payload: TriggerReportRequest, store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Trigger weekly report asynchronously."""

    week_start = payload.week_start.isoformat() if payload.week_start else None
    job_id = store.create_job_run("weekly_report", {"week_start": week_start})
    run_weekly_report.delay(week_start=week_start, job_run_id=str(job_id))
    return {"job_id": str(job_id)}


@app.post("/webhook/trigger-experiment")
def trigger_experiment(payload: TriggerExperimentRequest, store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Trigger growth experiment execution asynchronously."""

    job_id = store.create_job_run("growth_experiment_execution", {"experiment_id": payload.experiment_id})
    run_growth_experiment_execution.delay(experiment_id=payload.experiment_id, job_run_id=str(job_id))
    return {"job_id": str(job_id)}


@app.post("/webhook/trigger-experiment-planning")
def trigger_experiment_planning(store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Trigger growth experiment planning asynchronously."""

    job_id = store.create_job_run("growth_experiment_planning", {})
    run_growth_experiment_planning.delay(job_run_id=str(job_id))
    return {"job_id": str(job_id)}


@app.post("/admin/auto-mode", dependencies=[Depends(verify_admin_token)])
def set_auto_mode(payload: AutoModeRequest, store: MemoryStore = Depends(get_store)) -> dict[str, str]:
    """Update runtime AUTO_MODE without restart."""

    svc = SystemConfigService(store=store, settings=settings)
    mode = svc.set_auto_mode(payload.mode, updated_by="api_admin")
    return {"mode": mode}


@app.get("/")
def root() -> FileResponse:
    """Serve chat UI at root."""

    return FileResponse(CHAT_UI_FILE)


@app.get("/chat-ui")
def chat_ui() -> FileResponse:
    """Serve browser chat interface."""

    return FileResponse(CHAT_UI_FILE)


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """Interactive chat endpoint for direct agent conversations."""

    try:
        return _chat_generate(
            message=payload.message,
            history=payload.history,
            workload=payload.workload,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc


@app.post("/v1/chat/completions")
def openai_chat_completions(payload: OpenAIChatRequest) -> dict:
    """OpenAI-compatible chat endpoint for third-party UIs."""

    if payload.stream:
        raise HTTPException(status_code=400, detail="streaming is not supported")

    user_messages = [m for m in payload.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="at least one user message is required")

    last_user = user_messages[-1]
    history = [
        ChatTurn(role=m.role, content=m.content)
        for m in payload.messages[:-1]
        if m.role in {"user", "assistant", "system"}
    ]
    workload = payload.workload or ("heavy" if (payload.model or "").endswith("pro") else "standard")
    result = _chat_generate(message=last_user.content, history=history, workload=workload)

    completion_id = f"chatcmpl-{uuid4().hex[:24]}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(datetime.now(UTC).timestamp()),
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "total_tokens": result.input_tokens + result.output_tokens,
        },
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, store: MemoryStore = Depends(get_store)) -> dict:
    """Return async job state from job_runs table."""

    row = store.get_job_run(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return row


@app.get("/health")
def health(store: MemoryStore = Depends(get_store)) -> dict[str, Any]:
    """Health check for DB, Redis, and runtime dependencies."""

    db_state = "ok"
    redis_state = "ok"
    llm_state = "ok"
    outbox_state = "ok"

    try:
        store.health_check()
    except Exception:  # noqa: BLE001
        db_state = "fail"

    try:
        client = redis.from_url(settings.redis_url)
        client.ping()
    except Exception:  # noqa: BLE001
        redis_state = "fail"

    try:
        due = store.fetch_due_outbox_events(limit=1)
        if not isinstance(due, list):
            outbox_state = "degraded"
    except Exception:  # noqa: BLE001
        outbox_state = "fail"

    llm_probe: dict[str, Any] = {}
    try:
        runtime = get_runtime()
        content_agent = runtime["agents"]["content"]  # type: ignore[index]
        llm_probe = content_agent.router.probe(max_age_seconds=60)  # type: ignore[attr-defined]
        llm_state = llm_probe.get("status", "fail")
    except Exception:  # noqa: BLE001
        llm_state = "fail"

    payload: dict[str, Any] = {
        "status": "ok" if all(v in {"ok", "degraded"} for v in [db_state, redis_state, llm_state, outbox_state]) else "fail",
        "db": db_state,
        "redis": redis_state,
        "llm": llm_state,
        "outbox": outbox_state,
    }
    if llm_probe:
        payload["llm_probe"] = llm_probe
    return payload


@app.get("/metrics")
def metrics_stub() -> dict[str, str]:
    """Prometheus scrape stub for MVP."""

    return {"status": "ok"}


@app.get("/metrics/weekly")
def weekly_metrics(store: MemoryStore = Depends(get_store)) -> list[dict]:
    """Return latest weekly metrics window."""

    return store.get_weekly_metrics_window(limit=8)


@app.get("/content/recent")
def content_recent(store: MemoryStore = Depends(get_store)) -> list[dict]:
    """Return latest published content entries."""

    return store.get_recent_content(limit=10)
