from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands

from bot.utils.duel import (
    DIFFICULTY_LABELS,
    DuelDifficulty,
    generate_duel_id,
    get_random_word,
)
from bot.utils.duel_views import (
    DuelActivityView,
    DuelInviteView,
    build_duel_activity_embed,
    build_duel_invite_embed,
)

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)


def setup(bot: TajinHelper) -> None:
    @bot.tree.command(
        name="vagudle_duel",
        description="Challenge someone to a Vagudle duel with a randomly chosen word",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        difficulty="Normal: 11 guesses, common words — Hard: 9 guesses, uncommon words",
        word_length="How many letters the secret word will have (4–7)",
    )
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(
                name="Normal — 11 guesses, common words", value="normal"
            ),
            app_commands.Choice(name="Hard — 9 guesses, uncommon words", value="hard"),
        ],
        word_length=[
            app_commands.Choice(name="4 letters", value=4),
            app_commands.Choice(name="5 letters", value=5),
            app_commands.Choice(name="6 letters", value=6),
            app_commands.Choice(name="7 letters", value=7),
        ],
    )
    async def vagudle_duel(
        interaction: discord.Interaction,
        difficulty: app_commands.Choice[str],
        word_length: app_commands.Choice[int],
    ):
        logger.info(
            f"/vagudle_duel called by {interaction.user} (id={interaction.user.id}) "
            f"— difficulty='{difficulty.value}' word_length={word_length.value}"
        )

        diff: DuelDifficulty = difficulty.value  # type: ignore[assignment]

        word = get_random_word(diff, word_length.value)
        if word is None:
            await interaction.response.send_message(
                f"❌ Couldn't find a {word_length.value}-letter word for **{DIFFICULTY_LABELS[diff]}** difficulty. Try a different length.",
                ephemeral=True,
            )
            return

        player2_id: int | None = None
        opponent_name: str | None = None

        channel = interaction.channel
        if isinstance(channel, discord.DMChannel):
            recipient = getattr(channel, "recipient", None)
            if recipient is not None and recipient.id != interaction.user.id:
                player2_id = recipient.id
                opponent_name = recipient.display_name
                logger.info(
                    f"/vagudle_duel: detected DM, pre-assigned player2={player2_id} ({opponent_name})"
                )

        duel_id = generate_duel_id()

        view = DuelInviteView(
            player1_id=interaction.user.id,
            player2_id=player2_id,
            word=word,
            difficulty=diff,
            duel_id=duel_id,
        )

        embed = build_duel_invite_embed(
            interaction.user, diff, word_length.value, opponent_name
        )
        await interaction.response.send_message(embed=embed, view=view)
        logger.info(
            f"/vagudle_duel: posted invite, duel_id={duel_id} player1={interaction.user.id} player2={player2_id}"
        )

    @bot.tree.command(
        name="vagudle_duel_activity",
        description="Challenge someone to a Vagudle duel played live inside a Discord Activity",
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.describe(
        difficulty="Normal: 11 guesses, common words — Hard: 9 guesses, uncommon words",
        word_length="How many letters the secret word will have (4–7)",
        opponent="Optionally lock the challenge to a specific server member",
    )
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(
                name="Normal — 11 guesses, common words", value="normal"
            ),
            app_commands.Choice(name="Hard — 9 guesses, uncommon words", value="hard"),
        ],
        word_length=[
            app_commands.Choice(name="4 letters", value=4),
            app_commands.Choice(name="5 letters", value=5),
            app_commands.Choice(name="6 letters", value=6),
            app_commands.Choice(name="7 letters", value=7),
        ],
    )
    async def vagudle_duel_activity(
        interaction: discord.Interaction,
        difficulty: app_commands.Choice[str],
        word_length: app_commands.Choice[int],
        opponent: Optional[discord.Member] = None,
    ):
        logger.info(
            f"/vagudle_duel_activity called by {interaction.user} (id={interaction.user.id}) "
            f"— difficulty='{difficulty.value}' word_length={word_length.value} opponent={opponent}"
        )

        if opponent is not None and opponent.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You can't duel yourself.",
                ephemeral=True,
            )
            return

        diff: DuelDifficulty = difficulty.value  # type: ignore[assignment]

        word = get_random_word(diff, word_length.value)
        if word is None:
            await interaction.response.send_message(
                f"❌ Couldn't find a {word_length.value}-letter word for **{DIFFICULTY_LABELS[diff]}** difficulty. Try a different length.",
                ephemeral=True,
            )
            return

        player2_id: int | None = opponent.id if opponent is not None else None
        opponent_name: str | None = (
            opponent.display_name if opponent is not None else None
        )

        app_id = interaction.client.application_id
        if app_id is None:
            await interaction.response.send_message(
                "Bot is not ready yet. Please try again.", ephemeral=True
            )
            return

        duel_id = generate_duel_id()

        view = DuelActivityView(
            player1_id=interaction.user.id,
            player2_id=player2_id,
            word=word,
            difficulty=diff,
            duel_id=duel_id,
            application_id=app_id,
        )

        embed = build_duel_activity_embed(
            interaction.user, diff, word_length.value, opponent_name
        )
        await interaction.response.send_message(embed=embed, view=view)
        logger.info(
            f"/vagudle_duel_activity: posted invite, duel_id={duel_id} "
            f"player1={interaction.user.id} player2={player2_id}"
        )
