from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)


def setup(bot: TajinHelper) -> None:
    @bot.tree.command(
        name="vagudle_daily_channel",
        description="Set the channel where today's Vagudle Daily progress gets posted",
    )
    @app_commands.describe(channel="The channel to post daily progress/recaps in")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def vagudle_daily_channel(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        logger.info(
            f"/vagudle_daily_channel called by {interaction.user} (id={interaction.user.id}) "
            f"in guild {interaction.guild_id} — channel={channel.id}"
        )

        if not interaction.guild_id:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        ok = await bot.kv.store_daily_channel(
            str(interaction.guild_id), str(channel.id)
        )

        if ok:
            await interaction.response.send_message(
                f"✅ Vagudle Daily progress will now be posted in {channel.mention}.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "❌ Something went wrong saving that setting. Please try again.",
                ephemeral=True,
            )
