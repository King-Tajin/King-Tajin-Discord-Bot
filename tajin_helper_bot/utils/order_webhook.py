from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import aiohttp
import discord
from aiohttp import web

from tajin_helper_bot.config import Config
from tajin_helper_bot.utils.embeds import create_order_embed

if TYPE_CHECKING:
    from tajin_helper_bot.main import TajinHelper

logger = logging.getLogger(__name__)


async def announce_new_order(bot: TajinHelper, total: str | None, items: list) -> None:
    if not Config.STATS_CHANNEL_ID:
        logger.warning("announce_new_order: STATS_CHANNEL_ID not configured")
        return

    channel = bot.get_channel(int(Config.STATS_CHANNEL_ID))
    if not isinstance(channel, discord.TextChannel):
        logger.warning(
            f"announce_new_order: channel {Config.STATS_CHANNEL_ID} not found"
        )
        return

    embed = create_order_embed(total, items)

    try:
        message = await channel.send(embed=embed)

        if hasattr(channel, "is_news") and channel.is_news():
            try:
                await message.publish()
            except discord.HTTPException as e:
                logger.error(f"announce_new_order: failed to publish: {e}")

        logger.info("announce_new_order: posted new order announcement")
    except discord.Forbidden:
        logger.error(f"announce_new_order: no permission to post in {channel.id}")
    except discord.HTTPException as e:
        logger.error(f"announce_new_order: failed to send message: {e}")


async def handle_order_webhook(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Webhook-Secret", "")
    if not Config.ORDER_WEBHOOK_SECRET or secret != Config.ORDER_WEBHOOK_SECRET:
        logger.warning("handle_order_webhook: rejected request with invalid secret")
        return web.Response(status=401)

    try:
        data = await request.json()
    except (json.JSONDecodeError, aiohttp.ContentTypeError):
        return web.Response(status=400, text="Invalid JSON")

    total = data.get("total")
    items = data.get("items", [])

    bot: TajinHelper = request.app["bot"]
    await announce_new_order(bot, total, items)

    logger.info("handle_order_webhook: order announcement handled")
    return web.Response(status=200)


def register_order_routes(app: web.Application) -> None:
    app.router.add_post("/webhook/order", handle_order_webhook)


async def start_webhook_server(bot: TajinHelper) -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    register_order_routes(app)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server listening on port {Config.WEBHOOK_PORT}")
    return runner
