from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import aiohttp
from aiohttp import web

from bot.config import Config
from bot.utils.duel import DIFFICULTY_CONFIG
from bot.utils.embeds import (
    add_group_streak_footer,
    build_daily_progress_embed,
    build_daily_reminder_embed,
)

if TYPE_CHECKING:
    from bot.main import TajinHelper

logger = logging.getLogger(__name__)

_daily_locks: dict[str, asyncio.Lock] = {}

_WEEKDAY_SCHEDULE: dict[int, tuple[int, str]] = {
    0: (4, "hard"),
    1: (5, "normal"),
    2: (5, "hard"),
    3: (4, "normal"),
    4: (5, "hard"),
    5: (4, "hard"),
    6: (4, "normal"),
}


def _lock_key(group_id: str, date_str: str) -> str:
    return f"{group_id}:{date_str}"


def _get_daily_lock(group_id: str, date_str: str) -> asyncio.Lock:
    key = _lock_key(group_id, date_str)
    if key not in _daily_locks:
        _daily_locks[key] = asyncio.Lock()
    return _daily_locks[key]


def get_daily_word_config(date_str: str) -> tuple[int, int]:
    parsed = datetime.strptime(date_str, "%Y-%m-%d")
    word_length, difficulty = _WEEKDAY_SCHEDULE[parsed.weekday()]
    max_guesses = DIFFICULTY_CONFIG[difficulty]["guesses"]
    return word_length, max_guesses


def compute_daily_number(date_str: str) -> int:
    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
    epoch = datetime.strptime(Config.DAILY_EPOCH_DATE, "%Y-%m-%d").date()
    return (parsed - epoch).days + 1


async def _resolve_post_channel_id(
    bot: TajinHelper, group_id: str, group_type: str
) -> Optional[str]:
    if group_type == "server":
        channel_id = await bot.kv.get_daily_channel(group_id)
        if not channel_id:
            logger.warning(
                f"_resolve_post_channel_id: no daily channel configured for guild {group_id}, "
                f"skipping post (use /vagudle_daily_channel to set one)"
            )
            return None
        return channel_id

    return group_id


async def _render_and_sync_message(
    bot: TajinHelper,
    group_id: str,
    group_type: str,
    date_str: str,
    progress: dict,
    streak: Optional[dict] = None,
) -> None:
    word_length, max_guesses = get_daily_word_config(date_str)
    daily_number = compute_daily_number(date_str)

    render_players = {}
    for uid, player in progress.get("players", {}).items():
        render_players[uid] = {
            **player,
            "guess_count": len(player.get("guesses", {})),
        }

    embed = build_daily_progress_embed(
        daily_number, date_str, word_length, max_guesses, render_players
    )
    add_group_streak_footer(embed, streak)
    embed_dict = dict(embed.to_dict())

    if bot.dm_client is None:
        logger.error(
            "_render_and_sync_message: vagudle bot client not configured "
            "(VAGUDLE_WORKER_URL/VAGUDLE_WORKER_SECRET) — cannot post daily progress"
        )
        return

    channel_id = progress.get("channel_id")
    if not channel_id:
        channel_id = await _resolve_post_channel_id(bot, group_id, group_type)
        if not channel_id:
            return
        progress["channel_id"] = str(channel_id)
    channel_id = str(channel_id)

    message_id = progress.get("message_id")

    if message_id:
        message_id = str(message_id)
        result = await bot.dm_client.edit_channel_message(
            channel_id, message_id, embed=embed_dict
        )
        if result.get("success"):
            await bot.kv.store_daily_progress(group_id, date_str, progress)
            return
        if not result.get("not_found"):
            logger.warning(
                f"_render_and_sync_message: failed to edit message {message_id} "
                f"in channel {channel_id}: {result.get('error')}"
            )
            return

    result = await bot.dm_client.send_channel_message(channel_id, embed=embed_dict)
    if not result.get("success"):
        logger.error(
            f"_render_and_sync_message: failed to send message to channel {channel_id}: "
            f"{result.get('error')}"
        )
        return

    progress["message_id"] = str(result["message_id"])
    await bot.kv.store_daily_progress(group_id, date_str, progress)


async def handle_daily_started(bot: TajinHelper, data: dict) -> None:
    uid = data.get("uid")
    discord_id = data.get("discord_id")
    group_id = data.get("group_id")
    group_type = data.get("group_type")
    date_str = data.get("date")

    if not all([uid, discord_id, group_id, group_type, date_str]):
        logger.warning(
            f"handle_daily_started: missing required fields in payload: {data}"
        )
        return

    uid = str(uid)
    discord_id = str(discord_id)
    group_id = str(group_id)
    group_type = str(group_type)
    date_str = str(date_str)

    async with _get_daily_lock(group_id, date_str):
        progress = await bot.kv.get_daily_progress(group_id, date_str) or {
            "players": {}
        }
        players = progress.setdefault("players", {})

        if uid in players:
            logger.debug(
                f"handle_daily_started: {uid} already tracked for {group_id}/{date_str}"
            )
            return

        players[uid] = {
            "discord_id": discord_id,
            "guesses": {},
            "finished": False,
            "won": False,
            "guesses_used": None,
        }

        await _render_and_sync_message(bot, group_id, group_type, date_str, progress)


async def handle_daily_guess(bot: TajinHelper, data: dict) -> None:
    uid = data.get("uid")
    discord_id = data.get("discord_id")
    group_id = data.get("group_id")
    group_type = data.get("group_type")
    date_str = data.get("date")
    guess_number = data.get("guess_number")
    statuses = data.get("statuses")

    if (
        not all([uid, discord_id, group_id, group_type, date_str])
        or guess_number is None
        or not statuses
    ):
        logger.warning(
            f"handle_daily_guess: missing required fields in payload: {data}"
        )
        return

    uid = str(uid)
    discord_id = str(discord_id)
    group_id = str(group_id)
    group_type = str(group_type)
    date_str = str(date_str)

    async with _get_daily_lock(group_id, date_str):
        progress = await bot.kv.get_daily_progress(group_id, date_str) or {
            "players": {}
        }
        players = progress.setdefault("players", {})

        player = players.setdefault(
            uid,
            {
                "discord_id": discord_id,
                "guesses": {},
                "finished": False,
                "won": False,
                "guesses_used": None,
            },
        )

        player["guesses"][str(guess_number)] = True

        await _render_and_sync_message(bot, group_id, group_type, date_str, progress)


async def handle_daily_finished(bot: TajinHelper, data: dict) -> None:
    uid = data.get("uid")
    discord_id = data.get("discord_id")
    group_id = data.get("group_id")
    group_type = data.get("group_type")
    date_str = data.get("date")
    won = data.get("won")
    guesses_used = data.get("guesses_used")
    grid = data.get("grid")

    if not all([uid, discord_id, group_id, group_type, date_str]) or won is None:
        logger.warning(
            f"handle_daily_finished: missing required fields in payload: {data}"
        )
        return

    uid = str(uid)
    discord_id = str(discord_id)
    group_id = str(group_id)
    group_type = str(group_type)
    date_str = str(date_str)

    async with _get_daily_lock(group_id, date_str):
        progress = await bot.kv.get_daily_progress(group_id, date_str) or {
            "players": {}
        }
        players = progress.setdefault("players", {})

        player = players.setdefault(
            uid,
            {
                "discord_id": discord_id,
                "guesses": {},
                "finished": False,
                "won": False,
                "guesses_used": None,
            },
        )
        player["finished"] = True
        player["won"] = bool(won)
        player["guesses_used"] = guesses_used
        player["grid"] = grid or []

        streak = await bot.d1.get_group_streak(group_id, group_type)
        await _render_and_sync_message(
            bot, group_id, group_type, date_str, progress, streak
        )


_EVENT_HANDLERS = {
    "started": handle_daily_started,
    "guess": handle_daily_guess,
    "finished": handle_daily_finished,
}


async def handle_daily_webhook(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Daily-Secret", "")
    if not Config.DAILY_WEBHOOK_SECRET or secret != Config.DAILY_WEBHOOK_SECRET:
        logger.warning("handle_daily_webhook: rejected request with invalid secret")
        return web.Response(status=401)

    try:
        data = await request.json()
    except (json.JSONDecodeError, aiohttp.ContentTypeError):
        return web.Response(status=400, text="Invalid JSON")

    event = data.get("event")
    handler = _EVENT_HANDLERS.get(event)
    if handler is None:
        return web.Response(status=400, text=f"Unknown event '{event}'")

    bot: TajinHelper = request.app["bot"]
    asyncio.create_task(handler(bot, data))

    logger.info(
        f"handle_daily_webhook: queued '{event}' event for group {data.get('group_id')}"
    )
    return web.Response(status=200)


async def check_and_send_daily_reminders(bot: TajinHelper) -> None:
    if bot.dm_client is None:
        logger.error(
            "check_and_send_daily_reminders: vagudle bot client not configured, skipping"
        )
        return

    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()
    cutoff_str = (today - timedelta(days=3)).isoformat()

    recently_active_groups = await bot.d1.get_active_daily_groups_since(cutoff_str)
    today_groups = await bot.d1.get_active_daily_groups(today_str)
    today_keys = {
        (str(row["group_id"]), str(row["group_type"])) for row in today_groups
    }

    daily_number = compute_daily_number(today_str)
    embed = build_daily_reminder_embed(daily_number, today_str)
    embed_dict = dict(embed.to_dict())

    for row in recently_active_groups:
        group_id = str(row["group_id"])
        group_type = str(row["group_type"])

        if (group_id, group_type) in today_keys:
            continue

        channel_id = await _resolve_post_channel_id(bot, group_id, group_type)
        if not channel_id:
            continue

        result = await bot.dm_client.send_channel_message(channel_id, embed=embed_dict)
        if not result.get("success"):
            logger.warning(
                f"check_and_send_daily_reminders: failed to post reminder to channel "
                f"{channel_id} for group {group_id}: {result.get('error')}"
            )

    ok = await bot.d1.delete_old_daily_attempts()
    if not ok:
        logger.warning(
            "check_and_send_daily_reminders: failed to clean up old daily_attempts"
        )


def register_daily_routes(app: web.Application) -> None:
    app.router.add_post("/webhook/daily", handle_daily_webhook)
