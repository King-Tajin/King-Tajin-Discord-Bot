from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

import discord
from discord.http import Route

if TYPE_CHECKING:
    from vagudle_bot.main import VagudleBot

logger = logging.getLogger(__name__)

_ENTRY_POINT_COMMAND_TYPE = 4


def _hash_payload(payload: list[dict]) -> str:
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def _fetch_existing_commands(bot: VagudleBot) -> list[dict]:
    route = Route(
        "GET",
        "/applications/{application_id}/commands",
        application_id=bot.application_id,
    )
    return await bot.http.request(route)


async def sync_preserving_entry_point(
    bot: VagudleBot,
) -> list[discord.app_commands.AppCommand] | None:
    # noinspection PyProtectedMember
    commands = bot.tree._get_all_commands(guild=None)
    own_payload = [cmd.to_dict(bot.tree) for cmd in commands]
    own_hash = _hash_payload(own_payload)

    existing = await _fetch_existing_commands(bot)
    entry_point = next(
        (cmd for cmd in existing if cmd.get("type") == _ENTRY_POINT_COMMAND_TYPE),
        None,
    )
    existing_non_entry_point = [
        cmd for cmd in existing if cmd.get("type") != _ENTRY_POINT_COMMAND_TYPE
    ]
    existing_names = {cmd.get("name") for cmd in existing_non_entry_point}
    own_names = {cmd.get("name") for cmd in own_payload}

    last_synced_hash = await bot.kv.get_synced_commands_hash()

    if (
        last_synced_hash == own_hash
        and existing_names == own_names
        and len(existing_non_entry_point) == len(own_payload)
    ):
        logger.info(
            "sync_preserving_entry_point: command definitions unchanged and already "
            "registered on Discord, skipping sync"
        )
        return None

    payload = list(own_payload)
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

    await bot.kv.store_synced_commands_hash(own_hash)
    logger.info("sync_preserving_entry_point: synced and stored new command hash")

    # noinspection PyProtectedMember
    return [
        discord.app_commands.AppCommand(data=d, state=bot._connection) for d in data
    ]
