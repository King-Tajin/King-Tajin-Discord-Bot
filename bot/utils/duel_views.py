from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord

from bot.config import Config
from bot.utils.duel import (
    DIFFICULTY_CONFIG,
    DIFFICULTY_LABELS,
    DuelDifficulty,
    encode_duel,
    build_duel_url,
)

logger = logging.getLogger(__name__)

DUEL_INVITE_EXPIRY_HOURS = 24


def build_duel_invite_embed(
    challenger: discord.User | discord.Member,
    difficulty: str,
    word_length: int,
    opponent_name: str | None = None,
) -> discord.Embed:
    guesses = DIFFICULTY_CONFIG[difficulty]["guesses"]
    diff_label = DIFFICULTY_LABELS[difficulty]

    if opponent_name:
        description = f"**{challenger.display_name}** is challenging **{opponent_name}** to a Vagudle duel!"
    else:
        description = (
            f"**{challenger.display_name}** has issued a Vagudle duel challenge!"
        )

    embed = discord.Embed(
        title="⚔️ Vagudle Duel Challenge!",
        description=description,
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Difficulty", value=diff_label, inline=True)
    embed.add_field(name="Word Length", value=f"{word_length} letters", inline=True)
    embed.add_field(name="Guesses", value=str(guesses), inline=True)
    embed.set_footer(text="Results won't affect your stats. Links expire in 24 hours.")
    return embed


def build_duel_activity_embed(
    challenger: discord.User | discord.Member,
    difficulty: str,
    word_length: int,
    opponent_name: str | None = None,
) -> discord.Embed:
    guesses = DIFFICULTY_CONFIG[difficulty]["guesses"]
    diff_label = DIFFICULTY_LABELS[difficulty]

    if opponent_name:
        description = f"**{challenger.display_name}** is challenging **{opponent_name}** to a Vagudle activity duel!"
    else:
        description = f"**{challenger.display_name}** has issued a Vagudle activity duel challenge!"

    embed = discord.Embed(
        title="🎮 Vagudle Activity Duel!",
        description=description,
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Difficulty", value=diff_label, inline=True)
    embed.add_field(name="Word Length", value=f"{word_length} letters", inline=True)
    embed.add_field(name="Guesses", value=str(guesses), inline=True)
    embed.set_footer(
        text="Discord will prompt you to join a voice channel · Expires in 24 hours"
    )
    return embed


def _is_duel_invite_expired(message: discord.Message) -> bool:
    age = datetime.now(timezone.utc) - message.created_at
    return age > timedelta(hours=DUEL_INVITE_EXPIRY_HOURS)


class DuelInviteView(discord.ui.View):
    def __init__(
        self,
        player1_id: int,
        player2_id: int | None,
        word: str,
        difficulty: DuelDifficulty,
        duel_id: str,
    ):
        super().__init__(timeout=None)
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.word = word
        self.difficulty = difficulty
        self.duel_id = duel_id
        self.player1_accepted = False
        self.player2_accepted = False
        self._lock = asyncio.Lock()

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        logger.error(f"DuelInviteView error: {error}")
        try:
            await interaction.response.send_message(
                "Something went wrong. Please try again.", ephemeral=True
            )
        except discord.HTTPException:
            pass

    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.Forbidden:
            pass
        except (discord.HTTPException, AttributeError) as e:
            logger.warning(f"DuelInviteView: could not disable buttons: {e}")
        self.stop()

    async def _check_expired(self, interaction: discord.Interaction) -> bool:
        if interaction.message and _is_duel_invite_expired(interaction.message):
            await self._disable_buttons(interaction)
            await interaction.response.send_message(
                "⏰ This duel invite has expired. Use `/vagudle_duel` to start a new one.",
                ephemeral=True,
            )
            logger.info(
                f"DuelInviteView: duel {self.duel_id} invite expired, buttons disabled"
            )
            return True
        return False

    @discord.ui.button(label="Get My Link", style=discord.ButtonStyle.primary)
    async def player1_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.player1_id:
            await interaction.response.send_message(
                "Only the challenger can use this button.", ephemeral=True
            )
            return

        if await self._check_expired(interaction):
            return

        async with self._lock:
            if self.player1_accepted:
                await interaction.response.send_message(
                    "You've already generated your link.", ephemeral=True
                )
                return
            self.player1_accepted = True

        encoded = encode_duel(
            self.word, self.difficulty, self.duel_id, str(self.player1_id)
        )
        url = build_duel_url(Config.VAGUDLE_URL, encoded)
        generated_at = datetime.now(timezone.utc).isoformat()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        await interaction.client.d1.insert_duel_stub(
            duel_id=self.duel_id,
            discord_id=str(self.player1_id),
            word=self.word,
            word_length=len(self.word),
            dict_type=cfg["dict"],
            max_guesses=cfg["guesses"],
            generated_at=generated_at,
        )

        await interaction.response.send_message(
            f"Here's your duel link — keep it private!\n{url}",
            ephemeral=True,
        )

        if self.player1_accepted and self.player2_accepted:
            await self._disable_buttons(interaction)

    @discord.ui.button(label="Accept Duel", style=discord.ButtonStyle.success)
    async def player2_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if interaction.user.id == self.player1_id:
            await interaction.response.send_message(
                "You're the challenger — use the other button.", ephemeral=True
            )
            return

        if await self._check_expired(interaction):
            return

        async with self._lock:
            if self.player2_accepted:
                await interaction.response.send_message(
                    "The duel has already been accepted.", ephemeral=True
                )
                return

            if self.player2_id is not None and interaction.user.id != self.player2_id:
                await interaction.response.send_message(
                    "This duel challenge is not for you.", ephemeral=True
                )
                return

            if self.player2_id is None:
                self.player2_id = interaction.user.id

            self.player2_accepted = True

        encoded = encode_duel(
            self.word, self.difficulty, self.duel_id, str(self.player2_id)
        )
        url = build_duel_url(Config.VAGUDLE_URL, encoded)
        generated_at = datetime.now(timezone.utc).isoformat()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        await interaction.client.d1.insert_duel_stub(
            duel_id=self.duel_id,
            discord_id=str(self.player2_id),
            word=self.word,
            word_length=len(self.word),
            dict_type=cfg["dict"],
            max_guesses=cfg["guesses"],
            generated_at=generated_at,
        )

        await interaction.response.send_message(
            f"You've accepted the duel! Here's your link — keep it private!\n{url}",
            ephemeral=True,
        )

        if self.player1_accepted and self.player2_accepted:
            await self._disable_buttons(interaction)


class DuelActivityView(discord.ui.View):
    def __init__(
        self,
        player1_id: int,
        player2_id: int | None,
        word: str,
        difficulty: DuelDifficulty,
        duel_id: str,
        application_id: int,
    ):
        super().__init__(timeout=None)
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.word = word
        self.difficulty = difficulty
        self.duel_id = duel_id
        self.application_id = application_id
        self.player1_accepted = False
        self.player2_accepted = False
        self._lock = asyncio.Lock()

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        logger.error(f"DuelActivityView error: {error}")
        try:
            await interaction.response.send_message(
                "Something went wrong. Please try again.", ephemeral=True
            )
        except discord.HTTPException:
            pass

    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.Forbidden:
            pass
        except (discord.HTTPException, AttributeError) as e:
            logger.warning(f"DuelActivityView: could not disable buttons: {e}")
        self.stop()

    async def _check_expired(self, interaction: discord.Interaction) -> bool:
        if interaction.message and _is_duel_invite_expired(interaction.message):
            await self._disable_buttons(interaction)
            await interaction.response.send_message(
                "⏰ This duel invite has expired. Use `/vagudle_duel_activity` to start a new one.",
                ephemeral=True,
            )
            logger.info(
                f"DuelActivityView: duel {self.duel_id} invite expired, buttons disabled"
            )
            return True
        return False

    def _make_launch_view(self, encoded: str) -> discord.ui.View:
        activity_url = (
            f"https://discord.com/activities/{self.application_id}?duel={encoded}"
        )
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="▶ Launch Activity",
                url=activity_url,
            )
        )
        return view

    @discord.ui.button(label="Get My Link", style=discord.ButtonStyle.primary)
    async def player1_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.player1_id:
            await interaction.response.send_message(
                "Only the challenger can use this button.", ephemeral=True
            )
            return

        if await self._check_expired(interaction):
            return

        async with self._lock:
            if self.player1_accepted:
                await interaction.response.send_message(
                    "You've already generated your link.", ephemeral=True
                )
                return
            self.player1_accepted = True

        encoded = encode_duel(
            self.word, self.difficulty, self.duel_id, str(self.player1_id)
        )
        generated_at = datetime.now(timezone.utc).isoformat()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        await interaction.client.d1.insert_duel_stub(
            duel_id=self.duel_id,
            discord_id=str(self.player1_id),
            word=self.word,
            word_length=len(self.word),
            dict_type=cfg["dict"],
            max_guesses=cfg["guesses"],
            generated_at=generated_at,
        )

        await interaction.response.send_message(
            "Click the button below to launch the activity in your voice channel!",
            view=self._make_launch_view(encoded),
            ephemeral=True,
        )
        logger.info(
            f"DuelActivityView: player1 {self.player1_id} got activity link for duel {self.duel_id}"
        )

        if self.player1_accepted and self.player2_accepted:
            await self._disable_buttons(interaction)

    @discord.ui.button(label="Accept Duel", style=discord.ButtonStyle.success)
    async def player2_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if interaction.user.id == self.player1_id:
            await interaction.response.send_message(
                "You're the challenger — use the other button.", ephemeral=True
            )
            return

        if await self._check_expired(interaction):
            return

        async with self._lock:
            if self.player2_accepted:
                await interaction.response.send_message(
                    "The duel has already been accepted.", ephemeral=True
                )
                return

            if self.player2_id is not None and interaction.user.id != self.player2_id:
                await interaction.response.send_message(
                    "This duel challenge is not for you.", ephemeral=True
                )
                return

            if self.player2_id is None:
                self.player2_id = interaction.user.id

            self.player2_accepted = True

        encoded = encode_duel(
            self.word, self.difficulty, self.duel_id, str(self.player2_id)
        )
        generated_at = datetime.now(timezone.utc).isoformat()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        await interaction.client.d1.insert_duel_stub(
            duel_id=self.duel_id,
            discord_id=str(self.player2_id),
            word=self.word,
            word_length=len(self.word),
            dict_type=cfg["dict"],
            max_guesses=cfg["guesses"],
            generated_at=generated_at,
        )

        await interaction.response.send_message(
            "You've accepted the duel! Click the button below to launch the activity in your voice channel!",
            view=self._make_launch_view(encoded),
            ephemeral=True,
        )
        logger.info(
            f"DuelActivityView: player2 {self.player2_id} got activity link for duel {self.duel_id}"
        )

        if self.player1_accepted and self.player2_accepted:
            await self._disable_buttons(interaction)
