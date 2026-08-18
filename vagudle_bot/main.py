from __future__ import annotations

import logging
from datetime import time, datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks

from vagudle_bot.config import Config
from vagudle_bot.utils.cloudflare import CloudflareKV, CloudflareD1
from vagudle_bot.utils.daily_logic import check_and_send_daily_reminders
from vagudle_bot.utils.duel_logic import (
    start_webhook_server,
    build_expired_duel_embed,
    send_dm,
)
from vagudle_bot.utils.stats_helpers import fmt_diff, get_last_posted_duel_stats
from vagudle_bot.utils.embeds import (
    get_vagudle_embed,
    get_challenge_embed,
    get_daily_embed,
)
from vagudle_bot.utils.command_sync import sync_preserving_entry_point

import vagudle_bot.commands.challenge as cmd_challenge
import vagudle_bot.commands.daily as cmd_daily
import vagudle_bot.commands.duel as cmd_duel
import vagudle_bot.commands.leaderboard as cmd_leaderboard

logger = logging.getLogger(__name__)

_STALE_DUEL_DM_BATCH = 10


class VagudleBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

        self.kv: CloudflareKV | None = None
        self.d1: CloudflareD1 | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self._webhook_runner = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()

        self.kv = CloudflareKV(session=self.http_session)
        self.d1 = CloudflareD1(session=self.http_session)

        self._webhook_runner = await start_webhook_server(self)

        cmd_challenge.setup(self)
        cmd_daily.setup(self)
        cmd_duel.setup(self)
        cmd_leaderboard.setup(self)

        try:
            await sync_preserving_entry_point(self)
        except discord.HTTPException as e:
            logger.error(f"setup_hook: command sync failed, continuing without it: {e}")

        self.update_duel_stats.start()
        self.cleanup_stale_duels.start()
        self.send_daily_reminders.start()

    async def close(self):
        if self._webhook_runner:
            await self._webhook_runner.cleanup()
        if self.http_session:
            await self.http_session.close()
        await super().close()

    @tasks.loop(time=[time(hour=14, minute=45)])
    async def update_duel_stats(self):
        logger.info("update_duel_stats: task fired")
        try:
            now = datetime.now(timezone.utc)
            if now.weekday() not in (0, 4):
                return

            if not Config.STATS_CHANNEL_ID:
                logger.warning("update_duel_stats: STATS_CHANNEL_ID not configured")
                return

            channel = self.get_channel(int(Config.STATS_CHANNEL_ID))
            if not isinstance(channel, discord.TextChannel):
                logger.error(
                    f"update_duel_stats: channel {Config.STATS_CHANNEL_ID} not found or not a text channel"
                )
                return

            bot_user = self.user
            if not bot_user:
                return

            kv_data = await self.kv.get_value("vagudle_duels_played")
            duels_played = int(kv_data.get("count", 0)) if kv_data else 0

            last_stats = await get_last_posted_duel_stats(channel, bot_user)

            should_post = False
            changes = []

            if last_stats is None:
                should_post = True
                logger.info(
                    "update_duel_stats: no previous post found, posting initial stats"
                )
            else:
                diff = duels_played - last_stats.get("duels_played", 0)
                if diff != 0:
                    should_post = True
                    changes.append(f"{fmt_diff(diff, str)} duels played")
                logger.info(f"update_duel_stats: duels_diff={diff:+}")

            if not should_post:
                logger.info("update_duel_stats: no changes, skipping post")
                return

            embed = discord.Embed(
                title="Vagudle Duel Stats Updated!",
                color=discord.Color.from_rgb(80, 0, 170),
                timestamp=datetime.now(timezone.utc),
            )
            if changes:
                embed.description = "Changes: " + ", ".join(changes)
            embed.add_field(
                name="Duels Played", value=f"**{duels_played:,}**", inline=True
            )

            try:
                message = await channel.send(embed=embed)
                if hasattr(channel, "is_news") and channel.is_news():
                    try:
                        await message.publish()
                    except discord.HTTPException as e:
                        logger.error(
                            f"update_duel_stats: failed to publish message: {e}"
                        )
                logger.info(f"update_duel_stats: posted to #{channel.name}")
            except discord.Forbidden:
                logger.error(
                    f"update_duel_stats: no permission to post in #{channel.name}"
                )
            except discord.HTTPException as e:
                logger.error(f"update_duel_stats: HTTP error posting: {e}")
        except Exception as e:
            logger.error(f"update_duel_stats task error: {e}")

    @update_duel_stats.before_loop
    async def before_update_duel_stats(self):
        await self.wait_until_ready()

    @tasks.loop(time=[time(hour=h, minute=0) for h in [3, 9, 15, 21]])
    async def cleanup_stale_duels(self):
        logger.info("cleanup_stale_duels: task fired")
        try:
            rows = await self.d1.get_stale_duel_data()

            if not rows:
                logger.info(
                    "cleanup_stale_duels: no stale incomplete stubs found, skipping delete"
                )
                return

            groups: dict[str, list[dict]] = {}
            for row in rows:
                duel_id = row.get("duel_id")
                if duel_id:
                    groups.setdefault(str(duel_id), []).append(row)

            notify_pairs: list[tuple[dict, dict]] = []

            for duel_id, duel_rows in groups.items():
                null_rows = [r for r in duel_rows if not r.get("completed_at")]
                completed_rows = [r for r in duel_rows if r.get("completed_at")]

                if completed_rows and null_rows:
                    completed_row = completed_rows[0]
                    for null_row in null_rows:
                        notify_pairs.append((null_row, completed_row))

            total_duels = len(groups)
            notify_count = len(notify_pairs)
            silent_count = total_duels - notify_count
            logger.info(
                f"cleanup_stale_duels: {total_duels} duel(s) to clean — "
                f"{notify_count} with a completed partner (will DM), "
                f"{silent_count} fully unplayed (silent delete)"
            )

            dm_sent = 0
            for null_row, completed_row in notify_pairs[:_STALE_DUEL_DM_BATCH]:
                dnf_id = null_row.get("discord_id")
                finished_id = completed_row.get("discord_id")

                for discord_id, is_dnf in ((dnf_id, True), (finished_id, False)):
                    if not discord_id:
                        continue
                    try:
                        embed = build_expired_duel_embed(is_dnf=is_dnf)
                        await send_dm(self, int(str(discord_id)), embed)
                        dm_sent += 1
                        logger.info(
                            f"cleanup_stale_duels: DMed user {discord_id} (is_dnf={is_dnf})"
                        )
                    except (
                        discord.NotFound,
                        discord.Forbidden,
                        discord.HTTPException,
                    ) as e:
                        logger.warning(
                            f"cleanup_stale_duels: could not DM user {discord_id}: {e}"
                        )

            if notify_count > _STALE_DUEL_DM_BATCH:
                logger.warning(
                    f"cleanup_stale_duels: {notify_count - _STALE_DUEL_DM_BATCH} notify pair(s) "
                    f"skipped this run due to DM batch cap, will be cleaned up by the DELETE anyway"
                )

            logger.info(f"cleanup_stale_duels: sent {dm_sent} DM(s)")

            deleted_ok = await self.d1.delete_stale_null_stubs()
            if deleted_ok:
                logger.info(
                    "cleanup_stale_duels: stale null stubs deleted successfully"
                )
            else:
                logger.error(
                    "cleanup_stale_duels: DELETE query failed — stubs not removed"
                )

        except Exception as e:
            logger.error(f"cleanup_stale_duels task error: {e}", exc_info=True)

    @cleanup_stale_duels.before_loop
    async def before_cleanup_stale_duels(self):
        await self.wait_until_ready()

    @tasks.loop(time=time(hour=18, minute=0))
    async def send_daily_reminders(self):
        logger.info("send_daily_reminders: task fired")
        try:
            await check_and_send_daily_reminders(self)
        except Exception as e:
            logger.error(f"send_daily_reminders task error: {e}", exc_info=True)

    @send_daily_reminders.before_loop
    async def before_send_daily_reminders(self):
        await self.wait_until_ready()


def create_bot() -> VagudleBot:
    Config.validate()
    bot = VagudleBot()

    @bot.event
    async def on_ready():
        print(f"{bot.user} has connected to Discord!")
        print(f"Bot is in {len(bot.guilds)} guilds")
        print("━" * 50)

        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=Config.STATUS_TEXT or "Vagudle",
            ),
        )

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        user_pinged = bot.user in message.mentions

        if user_pinged or isinstance(message.channel, discord.DMChannel):
            await message.channel.send(embed=get_vagudle_embed())
            await message.channel.send(embed=get_daily_embed())
            await message.channel.send(embed=get_challenge_embed())

        await bot.process_commands(message)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ):
        logger.error(
            f"Command error from {interaction.user} (id={interaction.user.id}): {error}"
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "An unexpected error occurred.", ephemeral=True
                )
        except discord.HTTPException:
            pass

    return bot


async def start():
    bot = create_bot()
    await bot.start(Config.BOT_TOKEN)


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(start())
