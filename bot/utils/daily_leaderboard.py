from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)

_DAILY_LEADERBOARD_PAGE_SIZE = 25
_DISCORD_UID_PREFIX = "discord:"


def process_daily_leaderboard_rows(rows: list[dict]) -> list[dict]:
    processed = []
    for row in rows:
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        played = wins + losses
        win_rate = (wins / played * 100) if played > 0 else 0.0
        processed.append({**row, "played": played, "win_rate": win_rate})
    return processed


def _sort_daily_leaderboard(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (-int(r.get("best_streak") or 0), -int(r.get("wins") or 0)),
    )


def _display_name(row: dict) -> str:
    return row.get("username") or f"uid:{str(row.get('uid', ''))[:8]}"


def _find_row_for_discord_user(
    rows: list[dict], discord_id: int
) -> tuple[int | None, dict | None]:
    target_uid = f"{_DISCORD_UID_PREFIX}{discord_id}"
    for i, row in enumerate(rows):
        if str(row.get("uid", "")) == target_uid:
            return i + 1, row
    return None, None


def _format_daily_leaderboard_table(rows: list[dict], start_rank: int) -> str:
    header = f"{'#':>2} {'Player':<14} {'W':>3} {'L':>3} {'Streak':>6} {'Best':>4}"
    separator = "─" * len(header)
    lines = [header, separator]

    for i, row in enumerate(rows):
        rank = start_rank + i
        name = _display_name(row)
        if len(name) > 14:
            name = name[:13] + "…"
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        streak = int(row.get("current_streak") or 0)
        best = int(row.get("best_streak") or 0)
        lines.append(
            f"{rank:>2} {name:<14} {wins:>3} {losses:>3} {streak:>6} {best:>4}"
        )

    return "```\n" + "\n".join(lines) + "\n```"


async def build_daily_leaderboard_embed(
    bot: TajinHelper,
    all_rows: list[dict],
    page: int,
    lookup_user: discord.User | None = None,
) -> tuple[discord.Embed, int]:
    sorted_rows = _sort_daily_leaderboard(all_rows)
    total_pages = max(1, math.ceil(len(sorted_rows) / _DAILY_LEADERBOARD_PAGE_SIZE))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * _DAILY_LEADERBOARD_PAGE_SIZE
    page_rows = sorted_rows[start_idx : start_idx + _DAILY_LEADERBOARD_PAGE_SIZE]

    embed = discord.Embed(
        title="🗓️ Vagudle Daily Leaderboard",
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(
        text=f"By best streak · Page {page}/{total_pages} · Streak = current run"
    )

    if not sorted_rows:
        embed.description = "No daily results yet."
        return embed, total_pages

    embed.description = _format_daily_leaderboard_table(page_rows, start_idx + 1)

    if lookup_user:
        rank, row = _find_row_for_discord_user(sorted_rows, lookup_user.id)
        if row and rank:
            wins = int(row.get("wins") or 0)
            losses = int(row.get("losses") or 0)
            streak = int(row.get("current_streak") or 0)
            best = int(row.get("best_streak") or 0)
            embed.add_field(
                name=f"{_display_name(row)}'s stats",
                value=(
                    f"Rank **#{rank}** · {wins}W-{losses}L · "
                    f"current streak {streak} · best streak {best}"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"{lookup_user.display_name}'s stats",
                value=(
                    "No daily results found for that account. Lookup only works for "
                    "players who signed into Vagudle Daily with Discord."
                ),
                inline=False,
            )

    return embed, total_pages


class DailyLeaderboardView(discord.ui.View):
    def __init__(
        self,
        bot: TajinHelper,
        all_rows: list[dict],
        interaction_user_id: int,
        page: int = 1,
        total_pages: int = 1,
        lookup_user: discord.User | None = None,
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.all_rows = all_rows
        self.interaction_user_id = interaction_user_id
        self.page = page
        self.total_pages = total_pages
        self.lookup_user = lookup_user
        self.message: discord.Message | None = None
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction_user_id:
            await interaction.response.send_message(
                "This leaderboard belongs to someone else. Run `/vagudle_daily_leaderboard` to get your own.",
                ephemeral=True,
            )
            return False
        return True

    async def _update(self, interaction: discord.Interaction) -> None:
        embed, self.total_pages = await build_daily_leaderboard_embed(
            self.bot,
            self.all_rows,
            self.page,
            self.lookup_user,
        )
        self._refresh_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if not await self._check_owner(interaction):
            return
        self.page = max(1, self.page - 1)
        await self._update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        if not await self._check_owner(interaction):
            return
        self.page = min(self.total_pages, self.page + 1)
        await self._update(interaction)
