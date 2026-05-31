from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
import discord
from aiohttp import web

from bot.config import Config
from bot.utils.cloudflare import D1_TABLE_LEADERBOARD_HARD, D1_TABLE_LEADERBOARD_NORMAL

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)

_STALE_DUEL_DM_BATCH = 10
_processed_duels: set[str] = set()


def _calc_duration_seconds(generated_at: str, completed_at: str) -> float | None:
    try:
        start = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return None


def _determine_duel_outcomes(r1: dict, r2: dict) -> tuple[bool, bool]:
    r1_got_word = bool(r1.get("won"))
    r2_got_word = bool(r2.get("won"))

    if not r1_got_word and not r2_got_word:
        return False, False

    if r1_got_word and not r2_got_word:
        return True, False

    if not r1_got_word and r2_got_word:
        return False, True

    r1_guesses = int(r1.get("guesses_used") or 0)
    r2_guesses = int(r2.get("guesses_used") or 0)

    if r1_guesses != r2_guesses:
        return r1_guesses < r2_guesses, r2_guesses < r1_guesses

    r1_time = _calc_duration_seconds(
        r1.get("generated_at", ""), r1.get("completed_at", "")
    )
    r2_time = _calc_duration_seconds(
        r2.get("generated_at", ""), r2.get("completed_at", "")
    )

    if r1_time is not None and r2_time is not None and r1_time != r2_time:
        return r1_time < r2_time, r2_time < r1_time

    return True, True


def _format_duration(generated_at: str, completed_at: str) -> str:
    try:
        start = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        total_seconds = max(0, int((end - start).total_seconds()))
        if total_seconds < 60:
            return f"{total_seconds}s"
        minutes, seconds = divmod(total_seconds, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    except (ValueError, TypeError):
        return "unknown"


def build_expired_duel_embed(*, is_dnf: bool) -> discord.Embed:
    if is_dnf:
        embed = discord.Embed(
            title="Duel Expired",
            description=(
                "Your duel link expired before you completed the game. "
                "Your opponent's result has been removed so nothing counted against either of you.\n\n"
                "Want to run it back? Use `/vagudle_duel` to start a fresh duel!"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
    else:
        embed = discord.Embed(
            title="Duel Expired",
            description=(
                "You completed your duel, but your opponent's link expired before they played. "
                "The result has been voided so nothing counted against either of you.\n\n"
                "Want to try again? Use `/vagudle_duel` to start a fresh duel!"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
    embed.set_footer(text="Duel links expire after 24 hours · /vagudle_duel to rematch")
    return embed


async def check_duel_completion(bot: TajinHelper, duel_id: str) -> None:
    try:
        if duel_id in _processed_duels:
            logger.debug(
                f"check_duel_completion: duel {duel_id} already processed, skipping"
            )
            return

        results = await bot.d1.get_duel_results(duel_id)

        if len(results) < 2:
            logger.info(
                f"check_duel_completion: duel {duel_id} only has {len(results)} result(s), waiting for both players"
            )
            return

        logger.info(
            f"check_duel_completion: duel {duel_id} complete, processing outcomes"
        )

        r1 = results[0]
        r2 = results[1]

        dict_type = r1.get("dict_type", "normal")
        leaderboard_table = (
            D1_TABLE_LEADERBOARD_NORMAL
            if dict_type == "normal"
            else D1_TABLE_LEADERBOARD_HARD
        )

        r1_duel_won, r2_duel_won = _determine_duel_outcomes(r1, r2)
        r1_id = str(r1.get("discord_id", ""))
        r2_id = str(r2.get("discord_id", ""))

        lb1_ok = await bot.d1.upsert_leaderboard(
            r1_id, r2_id, r1_duel_won, leaderboard_table
        )
        lb2_ok = await bot.d1.upsert_leaderboard(
            r2_id, r1_id, r2_duel_won, leaderboard_table
        )

        if not lb1_ok or not lb2_ok:
            logger.error(
                f"check_duel_completion: leaderboard upsert failed for duel {duel_id}, will retry on next webhook call"
            )
            return

        _processed_duels.add(duel_id)
        logger.info(f"check_duel_completion: leaderboard updated for duel {duel_id}")

        await bot.kv.increment_duels_played()
        logger.info(f"check_duel_completion: incremented vagudle_duels_played")

        word = str(r1.get("word", "?"))

        for result, opponent, duel_won, opp_duel_won in (
            (r1, r2, r1_duel_won, r2_duel_won),
            (r2, r1, r2_duel_won, r1_duel_won),
        ):
            discord_id = result.get("discord_id")
            guesses = result.get("guesses_used", "?")
            opp_guesses = opponent.get("guesses_used", "?")
            opp_got_word = bool(opponent.get("won"))
            opp_outcome = "Won" if opp_duel_won else "Lost"

            my_time = _format_duration(
                result.get("generated_at", ""), result.get("completed_at", "")
            )
            opp_time = _format_duration(
                opponent.get("generated_at", ""), opponent.get("completed_at", "")
            )

            guesses_label = f"{guesses} guess{'es' if guesses != 1 else ''}"
            opp_guesses_label = (
                f"{opp_guesses} guess{'es' if opp_guesses != 1 else ''}"
                if opp_got_word
                else "DNF"
            )

            if duel_won and opp_duel_won:
                outcome_line = "🤝 It's a tie!"
                color = discord.Color.gold()
            elif duel_won:
                outcome_line = "🏆 You won!"
                color = discord.Color.green()
            else:
                outcome_line = "💀 You lost."
                color = discord.Color.red()

            embed = discord.Embed(
                title="⚔️ Duel Complete!",
                description=outcome_line,
                color=color,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Word", value=word, inline=False)
            embed.add_field(name="Your guesses", value=guesses_label, inline=True)
            embed.add_field(name="Your time", value=my_time, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            embed.add_field(name="Opponent result", value=opp_outcome, inline=True)
            embed.add_field(
                name="Opponent guesses", value=opp_guesses_label, inline=True
            )
            embed.add_field(name="Opponent time", value=opp_time, inline=True)

            if discord_id is None:
                logger.warning(
                    "check_duel_completion: result missing discord_id, skipping DM"
                )
                continue

            try:
                user = await bot.fetch_user(int(str(discord_id)))
                await user.send(embed=embed)
                logger.info(f"check_duel_completion: DMed result to user {discord_id}")
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                logger.warning(
                    f"check_duel_completion: could not DM user {discord_id}: {e}"
                )

    except Exception as e:
        logger.error(
            f"check_duel_completion: unhandled exception for duel {duel_id}: {e}",
            exc_info=True,
        )


async def handle_duel_webhook(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Duel-Secret", "")
    if not Config.DUEL_WEBHOOK_SECRET or secret != Config.DUEL_WEBHOOK_SECRET:
        logger.warning("handle_duel_webhook: rejected request with invalid secret")
        return web.Response(status=401)

    try:
        data = await request.json()
    except (json.JSONDecodeError, aiohttp.ContentTypeError):
        return web.Response(status=400, text="Invalid JSON")

    duel_id = data.get("duel_id")
    if not duel_id:
        return web.Response(status=400, text="Missing duel_id")

    bot: TajinHelper = request.app["bot"]
    asyncio.create_task(check_duel_completion(bot, duel_id))

    logger.info(f"handle_duel_webhook: queued completion check for duel {duel_id}")
    return web.Response(status=200)


async def start_webhook_server(bot: TajinHelper) -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/webhook/duel", handle_duel_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.DUEL_WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server listening on port {Config.DUEL_WEBHOOK_PORT}")
    return runner
