"""``/ping`` slash command — gateway latency + version. Spec §2.2."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from butler.core.version import APP_VERSION

if TYPE_CHECKING:
    from butler.bot.client import ButlerBot


def format_ping_response(*, latency_ms: int, version: str, ready: bool) -> str:
    """Build the response body for ``/ping``. Matches spec §2.2 example."""
    ready_text = "true" if ready else "false"
    return f"Pong. gateway={latency_ms}ms, app=v{version}, ready={ready_text}"


class Ping(commands.Cog):
    """Health-check the bot's gateway connection."""

    def __init__(self, bot: ButlerBot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's gateway latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        async with self.bot.track_command(interaction, command_name="ping"):
            latency_ms = round(self.bot.latency * 1000)
            response = format_ping_response(
                latency_ms=latency_ms,
                version=APP_VERSION,
                ready=self.bot.is_ready(),
            )
            await interaction.response.send_message(response, ephemeral=True)


async def setup(bot: ButlerBot) -> None:
    await bot.add_cog(Ping(bot))
