"""Base class shared by all autonomous agents."""

from __future__ import annotations

import json
from typing import Any

import structlog

from core.settings import get_settings
from llm.router import LLMRouter
from memory.embeddings import EmbeddingService
from memory.context_builder import ContextBuilder
from memory.learner import Learner
from memory.store import MemoryStore


logger = structlog.get_logger(__name__)


class BaseAgent:
    """Base agent with prompt building, memory operations, and LLM execution."""

    TASK_TYPE = "generic"

    def __init__(self, memory_store: MemoryStore, tools: dict[str, Any]) -> None:
        self.settings = get_settings()
        self.memory_store = memory_store
        self.tools = tools
        self.router = LLMRouter(store=memory_store)
        self.embeddings = EmbeddingService()
        self.context_builder = ContextBuilder(store=memory_store)
        self.learner = Learner(store=memory_store)

    def build_system_prompt(
        self,
        task_description: str = "general_task",
        extra_context: str = "",
    ) -> str:
        """Build task-aware system prompt from AGENT/SKILL contracts + memory."""

        return self.context_builder.build(
            task_type=self.TASK_TYPE,
            task_description=task_description,
            extra_context=extra_context,
        )

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a generic LLM task with optional context."""

        context = context or {}
        system_prompt = self.build_system_prompt(task_description=task, extra_context=json.dumps(context, ensure_ascii=True))
        user_payload = json.dumps({"task": task, "context": context}, ensure_ascii=True)
        response = self.router.generate(system_prompt=system_prompt, user_prompt=user_payload)
        return {
            "text": response.text,
            "provider": response.provider,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }

    def _handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute registered tool and return serialized output."""

        tool = self.tools.get(tool_name)
        if tool is None:
            raise KeyError(f"tool not found: {tool_name}")

        if hasattr(tool, "execute"):
            result = tool.execute(tool_input)
        elif callable(tool):
            result = tool(**tool_input)
        else:
            raise TypeError(f"invalid tool type for {tool_name}")

        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=True)
        return str(result)

    def remember(self, content: str, memory_type: str, importance: int = 5) -> None:
        """Store an item in semantic memory."""

        self.memory_store.remember(content=content, memory_type=memory_type, importance=importance)

    def recall(
        self,
        query: str,
        top_k: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch top-k semantically similar memory items."""

        return self.memory_store.recall(query=query, top_k=top_k, memory_types=memory_types)
