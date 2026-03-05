"""Build runtime system prompts from AGENT.md, SKILL.md and semantic memory."""

from __future__ import annotations

from pathlib import Path

import structlog

from core.settings import get_settings
from memory.store import MemoryStore


logger = structlog.get_logger(__name__)

_AGENT_MD = Path(__file__).resolve().parent.parent / "AGENT.md"
_SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"

_SKILL_SECTIONS = {
    "content": "## Skill 1:",
    "community": "## Skill 2:",
    "feedback": "## Skill 3:",
    "experiment": "## Skill 4:",
    "report": "## Skill 5:",
}


class ContextBuilder:
    """Assemble stable identity + task skill + relevant memories."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.settings = get_settings()
        self._agent_template = _AGENT_MD.read_text(encoding="utf-8")
        self._skills_template = _SKILL_MD.read_text(encoding="utf-8")

    def build(
        self,
        task_type: str,
        task_description: str,
        extra_context: str = "",
    ) -> str:
        """Return final system prompt used by all agent LLM calls."""

        parts: list[str] = [self._render_agent_identity()]

        skill_block = self._extract_skill_section(task_type)
        if skill_block:
            parts.append("\n---\n\n" + skill_block)

        memories = self.store.recall(
            query=task_description,
            memory_types=["PERFORMANCE", "NEGATIVE", "FACTUAL", "EXPERIMENT", "COMMUNITY"],
            top_k=8,
        )
        if memories:
            mem_text = "\n".join(
                f"- [{item.get('memory_type', 'UNKNOWN')}] {str(item.get('content', ''))[:220]}"
                for item in memories
            )
            parts.append("\n---\n\n## Relevant Learned Signals\n" + mem_text)

        if extra_context.strip():
            parts.append("\n---\n\n## Extra Context\n" + extra_context.strip())

        prompt = "\n\n".join(parts)
        logger.debug(
            "context_built",
            task_type=task_type,
            task_description=task_description[:120],
            length=len(prompt),
        )
        return prompt

    def _render_agent_identity(self) -> str:
        return (
            self._agent_template.replace("{AGENT_NAME}", self.settings.agent_name)
            .replace("{AGENT_START_DATE}", self.settings.agent_start_date)
        )

    def _extract_skill_section(self, task_type: str) -> str:
        marker = _SKILL_SECTIONS.get(task_type.lower().strip())
        if not marker:
            return ""

        start = self._skills_template.find(marker)
        if start < 0:
            logger.warning("skill_section_marker_missing", task_type=task_type, marker=marker)
            return ""

        next_idx = self._skills_template.find("\n## Skill ", start + len(marker))
        if next_idx < 0:
            return self._skills_template[start:].strip()
        return self._skills_template[start:next_idx].strip()

