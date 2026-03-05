"""Base class shared by all autonomous agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from core.settings import get_settings
from llm.router import LLMRouter
from memory.embeddings import EmbeddingService
from memory.store import MemoryStore


logger = structlog.get_logger(__name__)


class BaseAgent:
    """Base agent with prompt building, memory operations, and LLM execution."""

    def __init__(self, memory_store: MemoryStore, tools: dict[str, Any]) -> None:
        self.settings = get_settings()
        self.memory_store = memory_store
        self.tools = tools
        self.router = LLMRouter(store=memory_store)
        self.embeddings = EmbeddingService()

    def build_system_prompt(self) -> str:
        """Build system prompt with identity, recent publications, and learned facts."""

        template_path = Path("prompts/system_base.txt")
        template = template_path.read_text(encoding="utf-8")

        recent = self.memory_store.get_recent_publications(days=30)
        recent_text = "\n".join(f"- {item['title']} ({item.get('url') or 'n/a'})" for item in recent[:15])
        recent_text = recent_text or "- Yayın yok"

        learned = self.memory_store.get_recent_memories(limit=20)
        learned_text = "\n".join(f"- {item['content']}" for item in learned)
        learned_text = learned_text or "- Kayıt yok"

        return template.format(
            agent_name=self.settings.agent_name,
            agent_start_date=self.settings.agent_start_date,
            recent_publications=recent_text,
            learned_facts=learned_text,
        )

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a generic LLM task with optional context."""

        context = context or {}
        system_prompt = self.build_system_prompt()
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

        embedding = self.embeddings.embed(content)
        self.memory_store.insert_memory(memory_type=memory_type, content=content, embedding=embedding, importance=importance)

    def recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Fetch top-k semantically similar memory items."""

        embedding = self.embeddings.embed(query)
        return self.memory_store.search_memory(embedding=embedding, top_k=top_k)
