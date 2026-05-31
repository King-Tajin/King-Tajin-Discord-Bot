from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from bot.utils.cloudflare import D1_TABLE_LEADERBOARD_HARD, D1_TABLE_LEADERBOARD_NORMAL

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)

_LEADERBOARD_PAGE_SIZE = 25


def process_leaderboard_rows(rows: list[dict]) -> list[dict]:
    processed = []
    for row in rows:
        opponents_won: list[str] = json.loads(row.get("opponents_won") or "[]")
        matches_played = int(row.get("matches_played") or 0)
        matches_won = int(row.get("matches_won") or 0)
        win_rate = (matches_won / matches_played * 100) if matches_played > 0 else 0.0
        processed.append(
            {**row, "unique_wins": len(opponents_won), "win_rate": win_rate}
        )
    return processed


def _sort_leaderboard(rows: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "unique":
        return sorted(rows, key=lambda r: (-r["unique_wins"], -r["win_rate"]))
    return sorted(rows, key=lambda r: (-r["matches_won"], -r["win_rate"]))


async def _resolve_usernames(
    bot: TajinHelper, discord_ids: list[str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    to_fetch: list[str] = []

    for did in discord_ids:
        cached = bot.get_user(int(did))
        if cached:
            result[did] = cached.display_name
        else:
            to_fetch.append(did)

    if to_fetch:
        fetched = await asyncio.gather(
            *[bot.fetch_user(int(did)) for did in to_fetch],
            return_exceptions=True,
        )
        for did, user in zip(to_fetch, fetched):
            if isinstance(user, discord.User):
                result[did] = user.display_name
            else:
                result[did] = f"#{did[-4:]}"

    return result


def _format_leaderboard_table(
    rows: list[dict], usernames: dict[str, str], start_rank: int
) -> str:
    header = f"{'#':>2} {'Player':<12} {'Pld':>3} {'Won':>3} {'Win%':>4} {'UWin':>4}"
    separator = "─" * len(header)
    lines = [header, separator]

    for i, row in enumerate(rows):
        rank = start_rank + i
        did = str(row.get("discord_id", ""))
        name = usernames.get(did, f"#{did[-4:]}")
        if len(name) > 12:
            name = name[:11] + "…"
        played = int(row.get("matches_played") or 0)
        wins = int(row.get("matches_won") or 0)
        win_pct = f"{row['win_rate']:.0f}%"
        uw = row["unique_wins"]
        lines.append(f"{rank:>2} {name:<12} {played:>3} {wins:>3} {win_pct:>4} {uw:>4}")

    return "```\n" + "\n".join(lines) + "\n```"


async def build_leaderboard_embed(
    bot: TajinHelper,
    all_rows: list[dict],
    page: int,
    sort_by: str,
    difficulty: str,
    lookup_user: discord.User | None = None,
) -> tuple[discord.Embed, int]:
    sorted_rows = _sort_leaderboard(all_rows, sort_by)
    total_pages = max(1, math.ceil(len(sorted_rows) / _LEADERBOARD_PAGE_SIZE))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * _LEADERBOARD_PAGE_SIZE
    page_rows = sorted_rows[start_idx : start_idx + _LEADERBOARD_PAGE_SIZE]

    ids_to_resolve = [str(r.get("discord_id", "")) for r in page_rows]

    lookup_rank: int | None = None
    lookup_row: dict | None = None
    if lookup_user:
        lookup_did = str(lookup_user.id)
        for i, row in enumerate(sorted_rows):
            if str(row.get("discord_id", "")) == lookup_did:
                lookup_rank = i + 1
                lookup_row = row
                if lookup_did not in ids_to_resolve:
                    ids_to_resolve.append(lookup_did)
                break

    usernames = await _resolve_usernames(bot, ids_to_resolve)

    diff_label = "Normal" if difficulty == "normal" else "Hard"
    sort_label = "unique wins" if sort_by == "unique" else "total wins"

    embed = discord.Embed(
        title="⚔️ Vagudle Duel Leaderboard",
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(
        text=f"{diff_label} difficulty · By {sort_label} · Page {page}/{total_pages} · UWin = unique wins"
    )

    if not sorted_rows:
        embed.description = "No duels played yet."
        return embed, total_pages

    embed.description = _format_leaderboard_table(page_rows, usernames, start_idx + 1)

    if lookup_user:
        name = usernames.get(str(lookup_user.id), lookup_user.display_name)
        if lookup_row and lookup_rank:
            played = int(lookup_row.get("matches_played") or 0)
            wins = int(lookup_row.get("matches_won") or 0)
            win_pct = f"{lookup_row['win_rate']:.0f}%"
            uw = lookup_row["unique_wins"]
            embed.add_field(
                name=f"{name}'s stats",
                value=f"Rank **#{lookup_rank}** · {played} played · {wins} wins · {win_pct} win rate · {uw} unique wins",
                inline=False,
            )
        else:
            embed.add_field(
                name=f"{name}'s stats", value="No duels played yet.", inline=False
            )

    return embed, total_pages


class LeaderboardView(discord.ui.View):
    def __init__(
        self,
        bot: TajinHelper,
        all_rows: list[dict],
        sort_by: str = "unique",
        difficulty: str = "normal",
        page: int = 1,
        total_pages: int = 1,
        lookup_user: discord.User | None = None,
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.all_rows = all_rows
        self.sort_by = sort_by
        self.difficulty = difficulty
        self.page = page
        self.total_pages = total_pages
        self.lookup_user = lookup_user
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.sort_btn.label = (
            "By unique wins" if self.sort_by == "unique" else "By total wins"
        )
        self.diff_btn.label = (
            "Normal mode" if self.difficulty == "normal" else "Hard mode"
        )
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages

    async def _update(self, interaction: discord.Interaction) -> None:
        table = (
            D1_TABLE_LEADERBOARD_NORMAL
            if self.difficulty == "normal"
            else D1_TABLE_LEADERBOARD_HARD
        )
        raw_rows = await self.bot.d1.get_leaderboard(table)
        self.all_rows = process_leaderboard_rows(raw_rows)
        embed, self.total_pages = await build_leaderboard_embed(
            self.bot,
            self.all_rows,
            self.page,
            self.sort_by,
            self.difficulty,
            self.lookup_user,
        )
        self._refresh_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="By unique wins", style=discord.ButtonStyle.secondary)
    async def sort_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        self.sort_by = "total" if self.sort_by == "unique" else "unique"
        self.page = 1
        await self._update(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        self.page = max(1, self.page - 1)
        await self._update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        self.page = min(self.total_pages, self.page + 1)
        await self._update(interaction)

    @discord.ui.button(label="Hard mode", style=discord.ButtonStyle.secondary)
    async def diff_btn(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        self.difficulty = "hard" if self.difficulty == "normal" else "normal"
        self.page = 1
        await self._update(interaction)
