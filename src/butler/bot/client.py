"""``ButlerBot`` — discord.py ``commands.Bot`` subclass with a command-tracking helper.

Cogs use :meth:`ButlerBot.track_command` to record latency + status of each
slash-command invocation into ``command_invocations`` (spec §8.2). Failures
in the tracking layer never break the user-facing response.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import discord
import structlog
from discord.ext import commands

from butler.repositories.usage import record_invocation

if TYPE_CHECKING:
    from butler.core.state import AppState


class ButlerBot(commands.Bot):
    """Discord client. Owns command tree + cog loading."""

    def __init__(self, *, state: AppState) -> None:
        intents = discord.Intents.default()
        # Message Content (privileged) is only required for /summary in M4.
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.state = state
        self._log = structlog.get_logger("butler.bot")

    async def setup_hook(self) -> None:
        # Load M1 cogs.
        await self.load_extension("butler.bot.cogs.ping")

        # Sync slash commands to the configured guild for fast iteration.
        # Global commands take ~1 hour to propagate; guild-scoped commands are instant.
        guild_id = self.state.settings.discord_guild_id
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self._log.info(
                "synced guild commands",
                guild_id=guild_id,
                count=len(synced),
            )
        else:
            self._log.warning(
                "DISCORD_GUILD_ID not set — slash commands not synced",
            )

    async def on_ready(self) -> None:
        user = self.user
        self._log.info(
            "discord ready",
            user=str(user) if user else None,
            user_id=user.id if user else None,
            latency_ms=round(self.latency * 1000),
        )

    @asynccontextmanager
    async def track_command(
        self,
        interaction: discord.Interaction,
        *,
        command_name: str,
    ) -> AsyncIterator[None]:
        """Record latency + status of a slash-command invocation.

        Wrap a command body with this; the row is persisted whether the body
        returns or raises. Re-raises any exception so discord.py's standard
        error handling still runs.
        """
        start = time.monotonic()
        status = "success"
        error_type: str | None = None
        error_message: str | None = None
        try:
            yield
        except Exception as exc:
            status = "failed"
            error_type = type(exc).__name__
            error_message = str(exc)[:500]
            raise
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            await record_invocation(
                self.state.session_factory,
                interaction_id=interaction.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
                command_name=command_name,
                status=status,
                latency_ms=elapsed_ms,
                error_type=error_type,
                error_message=error_message,
            )
