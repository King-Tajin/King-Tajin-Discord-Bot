from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands

from bot.utils.embeds import (
    create_feedback_embed,
    create_feedback_list_embed,
    create_stats_embed,
)
from bot.utils.helpers import check_guild

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)


def setup(bot: TajinHelper) -> None:
    @bot.tree.command(
        name="view_feedback", description="View a specific feedback by ID"
    )
    @app_commands.describe(feedback_id="The ID of the feedback to retrieve")
    async def get_feedback(interaction: discord.Interaction, feedback_id: str):
        logger.info(
            f"/view_feedback called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}'"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        feedback = await bot.kv.get_value(feedback_id)
        if feedback:
            embed = create_feedback_embed(feedback)
            await interaction.followup.send(embed=embed)
        else:
            logger.warning(f"/view_feedback: no feedback found for id='{feedback_id}'")
            await interaction.followup.send(
                f"No feedback found with ID: `{feedback_id}`"
            )

    @bot.tree.command(name="list_feedback", description="List all feedback entries")
    @app_commands.describe(
        sentiment="Filter by sentiment (positive, negative, neutral)",
        category="Filter by category",
    )
    async def list_feedback(
        interaction: discord.Interaction,
        sentiment: Optional[str] = None,
        category: Optional[str] = None,
    ):
        logger.info(
            f"/list_feedback called by {interaction.user} (id={interaction.user.id}) — sentiment={sentiment} category={category}"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        feedbacks = await bot.kv.get_all_feedbacks()
        if not feedbacks:
            await interaction.followup.send("No feedback entries found.")
            return
        if sentiment:
            feedbacks = [
                f for f in feedbacks if f.get("sentiment") == sentiment.lower()
            ]
        if category:
            feedbacks = [f for f in feedbacks if f.get("category") == category.lower()]
        if not feedbacks:
            await interaction.followup.send("No feedback entries match your filters.")
            return
        embed = create_feedback_list_embed(feedbacks)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(
        name="feedback_stats", description="Get statistics about feedback"
    )
    async def feedback_stats(interaction: discord.Interaction):
        logger.info(
            f"/feedback_stats called by {interaction.user} (id={interaction.user.id})"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        feedbacks = await bot.kv.get_all_feedbacks()
        if not feedbacks:
            await interaction.followup.send("No feedback entries found.")
            return
        embed = create_stats_embed(feedbacks)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="add_tag", description="Add a tag to a feedback entry")
    @app_commands.describe(
        feedback_id="The ID of the feedback to tag", tag="The tag to add"
    )
    async def add_tag(interaction: discord.Interaction, feedback_id: str, tag: str):
        logger.info(
            f"/add_tag called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}' tag='{tag}'"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        success = await bot.kv.add_tag(feedback_id, tag)
        if success:
            logger.info(f"/add_tag: successfully tagged '{feedback_id}' with '{tag}'")
            await interaction.followup.send(
                f"Successfully added tag `{tag}` to feedback `{feedback_id}`"
            )
        else:
            await interaction.followup.send(
                f"Failed to add tag. Feedback `{feedback_id}` not found."
            )

    @bot.tree.command(
        name="mark_completed", description="Mark a feedback entry as completed"
    )
    @app_commands.describe(feedback_id="The ID of the feedback to mark as completed")
    async def mark_completed(interaction: discord.Interaction, feedback_id: str):
        logger.info(
            f"/mark_completed called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}'"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        success = await bot.kv.mark_completed(feedback_id, True)
        if success:
            logger.info(f"/mark_completed: '{feedback_id}' marked completed")
            await interaction.followup.send(
                f"Successfully marked feedback `{feedback_id}` as completed"
            )
        else:
            await interaction.followup.send(
                f"Failed to update feedback. Feedback `{feedback_id}` not found."
            )

    @bot.tree.command(
        name="mark_pending", description="Mark a feedback entry as pending"
    )
    @app_commands.describe(feedback_id="The ID of the feedback to mark as pending")
    async def mark_pending(interaction: discord.Interaction, feedback_id: str):
        logger.info(
            f"/mark_pending called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}'"
        )
        if not await check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        success = await bot.kv.mark_completed(feedback_id, False)
        if success:
            logger.info(f"/mark_pending: '{feedback_id}' marked pending")
            await interaction.followup.send(
                f"Successfully marked feedback `{feedback_id}` as pending"
            )
        else:
            await interaction.followup.send(
                f"Failed to update feedback. Feedback `{feedback_id}` not found."
            )
