from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands

from bot.utils.cloudflare import D1_TABLE_LEADERBOARD_NORMAL
from bot.utils.leaderboard import (
    LeaderboardView,
    build_leaderboard_embed,
    process_leaderboard_rows,
)

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)


def setup(bot: TajinHelper) -> None:
    @bot.tree.command(
        name="vagudle_leaderboard",
        description="View the Vagudle duel leaderboard",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="Look up a specific player's rank and stats")
    async def vagudle_leaderboard(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
    ):
        logger.info(
            f"/vagudle_leaderboard called by {interaction.user} (id={interaction.user.id}) "
            f"— lookup={'@' + str(user) if user else 'none'}"
        )
        await interaction.response.defer()

        raw_rows = await bot.d1.get_leaderboard(D1_TABLE_LEADERBOARD_NORMAL)
        all_rows = process_leaderboard_rows(raw_rows)

        embed, total_pages = await build_leaderboard_embed(
            bot, all_rows, 1, "unique", "normal", user
        )

        view = LeaderboardView(
            bot=bot,
            all_rows=all_rows,
            interaction_user_id=interaction.user.id,
            sort_by="unique",
            difficulty="normal",
            page=1,
            total_pages=total_pages,
            lookup_user=user,
        )

        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg