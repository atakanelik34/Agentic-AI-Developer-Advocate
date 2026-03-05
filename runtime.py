"""Runtime object factory for tools, store, and agents."""

from __future__ import annotations

from agents.community_agent import CommunityAgent
from agents.content_agent import ContentAgent
from agents.feedback_agent import FeedbackAgent
from agents.report_agent import ReportAgent
from core.logging import configure_logging
from core.settings import get_settings
from memory.store import MemoryStore
from tools.discord_tool import DiscordTool
from tools.github_tool import GitHubTool
from tools.hashnode import HashnodeTool
from tools.revenuecat import RevenueCatTool
from tools.scraper import ScraperTool
from tools.twitter import TwitterTool


def build_runtime() -> dict[str, object]:
    """Instantiate app runtime dependencies."""

    settings = get_settings()
    configure_logging(settings.log_level)

    store = MemoryStore()
    tools = {
        "revenuecat": RevenueCatTool(),
        "hashnode": HashnodeTool(),
        "twitter": TwitterTool(),
        "github": GitHubTool(),
        "discord": DiscordTool(),
        "scraper": ScraperTool(),
    }

    agents = {
        "content": ContentAgent(memory_store=store, tools=tools),
        "community": CommunityAgent(memory_store=store, tools=tools),
        "feedback": FeedbackAgent(memory_store=store, tools=tools),
        "report": ReportAgent(memory_store=store, tools=tools),
    }

    return {
        "settings": settings,
        "store": store,
        "tools": tools,
        "agents": agents,
    }
