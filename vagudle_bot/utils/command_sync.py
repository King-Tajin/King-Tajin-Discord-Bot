from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.http import Route

if TYPE_CHECKING:
    from vagudle_bot.main import VagudleBot

logger = logging.getLogger(__name__)

_ENTRY_POINT_COMMAND_TYPE = 4


async def _fetch_entry_point_command(bot: VagudleBot) -> dict | None:
    route = Route(
        "GET",
        "/applications/{application_id}/commands",
        application_id=bot.application_id,
    )
    existing = await bot.http.request(route)
    return next(
        (cmd for cmd in existing if cmd.get("type") == _ENTRY_POINT_COMMAND_TYPE),
        None,
    )


async def sync_preserving_entry_point(
    bot: VagudleBot,
) -> list[discord.app_commands.AppCommand]:
    entry_point = await _fetch_entry_point_command(bot)

    # noinspection PyProtectedMember
    commands = bot.tree._get_all_commands(guild=None)
    payload = [cmd.to_dict(bot.tree) for cmd in commands]

    if entry_point:
        payload.append(entry_point)
        logger.info(
            f"sync_preserving_entry_point: preserving entry point command "
            f"'{entry_point.get('name')}' during global sync"
        )

    route = Route(
        "PUT",
        "/applications/{application_id}/commands",
        application_id=bot.application_id,
    )
    data = await bot.http.request(route, json=payload)
    # noinspection PyProtectedMember
    return [
        discord.app_commands.AppCommand(data=d, state=bot._connection) for d in data
    ]
