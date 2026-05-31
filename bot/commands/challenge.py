from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from bot.config import Config
from bot.utils.challenge import (
    ChallengeDict,
    DICT_DESCRIPTIONS,
    DICT_LABELS,
    build_challenge_url,
    encode_challenge,
    get_dict_hints,
    is_word_in_dict,
)

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)


def _build_challenge_embed(
    word: str,
    dict_type: ChallengeDict,
    guesses_val: int,
    url: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="Share with your friends!",
        description=f"{len(word)} letters · {DICT_LABELS[dict_type]} dictionary · {guesses_val} guesses",
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Challenge Link", value=url, inline=False)
    embed.set_footer(text="Results won't affect your stats.")
    return embed


class DictConfirmView(discord.ui.View):
    def __init__(
        self,
        word: str,
        selected_dict: ChallengeDict,
        easier_dict: ChallengeDict,
        guesses_val: int,
    ):
        super().__init__(timeout=60)
        self.word = word
        self.selected_dict = selected_dict
        self.easier_dict = easier_dict
        self.guesses_val = guesses_val

        self.keep_btn.label = f"Keep {DICT_LABELS[selected_dict]}"
        self.switch_btn.label = f"Switch to {DICT_LABELS[easier_dict]}"

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        logger.error(f"DictConfirmView error: {error}")
        try:
            await interaction.response.send_message(
                "Something went wrong generating the challenge. Please try again.",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    async def _send_challenge(
        self, interaction: discord.Interaction, dict_type: ChallengeDict
    ) -> None:
        try:
            await interaction.response.defer()
            encoded, challenge_id = encode_challenge(
                self.word, dict_type, self.guesses_val
            )
            url = build_challenge_url(Config.VAGUDLE_URL, encoded)
            logger.info(
                f"/vagudle_challenge (dict confirm): generated id={challenge_id} url={url}"
            )
            embed = _build_challenge_embed(self.word, dict_type, self.guesses_val, url)
            await interaction.followup.send(embed=embed)
            self.stop()
        except Exception as e:
            logger.error(f"DictConfirmView._send_challenge error: {e}")
            try:
                await interaction.followup.send(
                    "Something went wrong generating the challenge. Please try again.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def keep_btn(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._send_challenge(interaction, self.selected_dict)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def switch_btn(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._send_challenge(interaction, self.easier_dict)


class DictSwitchView(discord.ui.View):
    def __init__(self, word: str, target_dict: ChallengeDict, guesses_val: int):
        super().__init__(timeout=60)
        self.word = word
        self.target_dict = target_dict
        self.guesses_val = guesses_val
        self.use_btn.label = f"Use {DICT_LABELS[target_dict]}"

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        logger.error(f"DictSwitchView error: {error}")
        try:
            await interaction.response.send_message(
                "Something went wrong generating the challenge. Please try again.",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def use_btn(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        try:
            await interaction.response.defer()
            encoded, challenge_id = encode_challenge(
                self.word, self.target_dict, self.guesses_val
            )
            url = build_challenge_url(Config.VAGUDLE_URL, encoded)
            logger.info(
                f"/vagudle_challenge (dict switch): generated id={challenge_id} url={url}"
            )
            embed = _build_challenge_embed(
                self.word, self.target_dict, self.guesses_val, url
            )
            await interaction.followup.send(embed=embed)
            self.stop()
        except Exception as e:
            logger.error(f"DictSwitchView.use_btn error: {e}")
            try:
                await interaction.followup.send(
                    "Something went wrong generating the challenge. Please try again.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass


def setup(bot: TajinHelper) -> None:
    @bot.tree.command(
        name="vagudle_challenge",
        description="Create a Vagudle challenge — the dictionary only signals word popularity, not difficulty",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        word="The secret word (4–7 letters) — must exist in the chosen dictionary",
        dictionary="Which word list the challenger must guess from",
        guesses="How many attempts the challenger gets",
    )
    @app_commands.choices(
        dictionary=[
            app_commands.Choice(name="Normal — Common English words", value="normal"),
            app_commands.Choice(name="Hard — Uncommon English words", value="hard"),
            app_commands.Choice(
                name="Extreme — Full Scrabble dictionary", value="full"
            ),
        ],
        guesses=[
            app_commands.Choice(name="9 guesses", value=9),
            app_commands.Choice(name="11 guesses", value=11),
        ],
    )
    async def vagudle_challenge(
        interaction: discord.Interaction,
        word: str,
        dictionary: app_commands.Choice[str],
        guesses: app_commands.Choice[int],
    ):
        logger.info(
            f"/vagudle_challenge called by {interaction.user} (id={interaction.user.id}) "
            f"— word='{word}' dict='{dictionary.value}' guesses={guesses.value}"
        )

        clean = word.upper().replace(" ", "")

        if not clean.isalpha():
            await interaction.response.send_message(
                "❌ The word can only contain letters — no spaces, numbers, or symbols.",
                ephemeral=True,
            )
            return

        if len(clean) < 4 or len(clean) > 7:
            await interaction.response.send_message(
                f"❌ `{clean}` is {len(clean)} letter{'s' if len(clean) != 1 else ''} long. Words must be 4–7 letters.",
                ephemeral=True,
            )
            return

        dict_type: ChallengeDict = dictionary.value  # type: ignore[assignment]
        hints = get_dict_hints(clean, dict_type)

        if not is_word_in_dict(clean, dict_type):
            found_in: ChallengeDict | None = hints["found_in"]
            if found_in:
                await interaction.response.send_message(
                    f"❌ `{clean}` isn't in the **{DICT_LABELS[dict_type]}** dictionary "
                    f"({DICT_DESCRIPTIONS[dict_type].lower()}).\n"
                    f"`{clean}` does appear in the **{DICT_LABELS[found_in]}** dictionary "
                    f"({DICT_DESCRIPTIONS[found_in].lower()}) though.",
                    view=DictSwitchView(clean, found_in, guesses.value),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"❌ `{clean}` isn't in the **{DICT_LABELS[dict_type]}** dictionary "
                    f"or any of the other dictionaries. Try a different word.",
                    ephemeral=True,
                )
            return

        easier_than: ChallengeDict | None = hints["easier_than"]
        if easier_than:
            logger.info(
                f"/vagudle_challenge: '{clean}' also in easier dict '{easier_than}', prompting user"
            )
            view = DictConfirmView(clean, dict_type, easier_than, guesses.value)
            await interaction.response.send_message(
                f"⚠️ Heads up: `{clean}` also appears in the **{DICT_LABELS[easier_than]}** dictionary "
                f"({DICT_DESCRIPTIONS[easier_than].lower()}).\n\n"
                f"The dictionary doesn't affect gameplay difficulty — it only tells the player how "
                f"common the word is. Choosing **{DICT_LABELS[easier_than]}** gives the player more "
                f"precise information about the word's popularity.\n\n"
                f"Which dictionary would you like to use?",
                view=view,
                ephemeral=True,
            )
            return

        encoded, challenge_id = encode_challenge(clean, dict_type, guesses.value)
        url = build_challenge_url(Config.VAGUDLE_URL, encoded)

        logger.info(f"/vagudle_challenge: generated id={challenge_id} url={url}")

        embed = _build_challenge_embed(clean, dict_type, guesses.value, url)
        await interaction.response.send_message(embed=embed)
