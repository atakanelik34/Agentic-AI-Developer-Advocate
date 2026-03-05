"""Discord helper client."""

from __future__ import annotations

import asyncio
from typing import Any

import discord
from tenacity import retry, stop_after_attempt, wait_exponential

from core.settings import get_settings
from tools.errors import ToolExecutionError


class DiscordTool:
    """Post messages to Discord channel when enabled."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=1, max=4))
    def post_message(self, message: str) -> dict[str, Any]:
        """Send message to configured Discord channel."""

        if not self.settings.enable_discord:
            return {"skipped": True, "reason": "discord disabled"}
        if not self.settings.discord_bot_token or not self.settings.discord_channel_id:
            raise ToolExecutionError("discord not configured")

        async def _run() -> dict[str, Any]:
            intents = discord.Intents.default()
            client = discord.Client(intents=intents)
            result: dict[str, Any] = {}

            @client.event
            async def on_ready() -> None:
                channel = client.get_channel(int(self.settings.discord_channel_id))
                if channel is None:
                    await client.close()
                    raise ToolExecutionError("discord channel not found")
                sent = await channel.send(message)
                result["id"] = str(sent.id)
                await client.close()

            await client.start(self.settings.discord_bot_token)
            return result

        try:
            return asyncio.run(_run())
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"discord post failed: {exc}") from exc
