from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.config import Config
from bot.utils.curseforge import get_curseforge_stats
from bot.utils.embeds import create_curseforge_embed, create_modrinth_embed
from bot.utils.helpers import check_guild
from bot.utils.modrinth import get_modrinth_stats

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)


def setup(bot: TajinHelper) -> None:
    @bot.tree.command(
        name="curseforge_stats", description="Get CurseForge statistics for king_tajin"
    )
    async def curseforge_stats(interaction: discord.Interaction):
        logger.info(
            f"/curseforge_stats called by {interaction.user} (id={interaction.user.id})"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        stats = await get_curseforge_stats("king_tajin")
        if stats:
            if stats["followers"] is None:
                stats["followers"] = 0
            embed = create_curseforge_embed(stats)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(
                "Failed to retrieve CurseForge stats. Check bot logs for details."
            )

    @bot.tree.command(
        name="modrinth_stats", description="Get Modrinth statistics for King_Tajin"
    )
    async def modrinth_stats(interaction: discord.Interaction):
        logger.info(
            f"/modrinth_stats called by {interaction.user} (id={interaction.user.id})"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        stats = await get_modrinth_stats("King_Tajin")
        if stats:
            embed = create_modrinth_embed(stats)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(
                "Failed to retrieve Modrinth stats. Check bot logs for details."
            )

    @bot.tree.command(
        name="post_curseforge_stats",
        description="Manually post CurseForge stats to the stats channel",
    )
    async def post_curseforge_stats(interaction: discord.Interaction):
        logger.info(
            f"/post_curseforge_stats called by {interaction.user} (id={interaction.user.id})"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()

        if not Config.STATS_CHANNEL_ID:
            await interaction.followup.send("STATS_CHANNEL_ID not configured.")
            return

        stats = await get_curseforge_stats("king_tajin")
        if not stats:
            await interaction.followup.send("Failed to retrieve CurseForge stats.")
            return

        if stats["followers"] is None:
            stats["followers"] = 0

        channel = bot.get_channel(int(Config.STATS_CHANNEL_ID))
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                f"Channel {Config.STATS_CHANNEL_ID} not found."
            )
            return

        try:
            await bot.kv.store_curseforge_stats(stats)
            embed = create_curseforge_embed(stats)
            message = await channel.send(embed=embed)

            if hasattr(channel, "is_news") and channel.is_news():
                try:
                    await message.publish()
                except discord.HTTPException as e:
                    logger.error(f"/post_curseforge_stats: failed to publish: {e}")

            await interaction.followup.send(f"Posted stats to {channel.mention}")
        except discord.Forbidden:
            await interaction.followup.send(
                f"No permission to post in {channel.mention}"
            )
        except discord.HTTPException as e:
            if not interaction.is_expired():
                await interaction.followup.send(f"Error posting: {e}")

    @bot.tree.command(
        name="post_modrinth_stats",
        description="Manually post Modrinth stats to the stats channel",
    )
    async def post_modrinth_stats(interaction: discord.Interaction):
        logger.info(
            f"/post_modrinth_stats called by {interaction.user} (id={interaction.user.id})"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()

        if not Config.STATS_CHANNEL_ID:
            await interaction.followup.send("STATS_CHANNEL_ID not configured.")
            return

        stats = await get_modrinth_stats("King_Tajin")
        if not stats:
            await interaction.followup.send("Failed to retrieve Modrinth stats.")
            return

        channel_id = int(Config.STATS_CHANNEL_ID)
        channel = bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(f"Channel {channel_id} not found.")
            return

        try:
            await bot.kv.store_modrinth_stats(stats)
            embed = create_modrinth_embed(stats)
            message = await channel.send(embed=embed)

            if hasattr(channel, "is_news") and channel.is_news():
                try:
                    await message.publish()
                except discord.HTTPException as e:
                    logger.error(
                        f"/post_modrinth_stats: failed to publish message: {e}"
                    )

            await interaction.followup.send(f"Posted stats to {channel.mention}")
        except discord.Forbidden:
            await interaction.followup.send(
                f"No permission to post in {channel.mention}"
            )
        except discord.HTTPException as e:
            if not interaction.is_expired():
                await interaction.followup.send(f"Error posting: {e}")

    @bot.tree.command(
        name="clear_commands", description="Clear duplicate slash commands"
    )
    async def clear_commands(interaction: discord.Interaction):
        logger.info(
            f"/clear_commands called by {interaction.user} (id={interaction.user.id})"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        await interaction.followup.send(
            "Cleared all commands. Restart the bot to re-register them."
        )
