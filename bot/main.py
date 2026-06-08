from __future__ import annotations

import logging
from datetime import time, datetime, timezone, timedelta

import aiohttp
import discord
from discord.ext import commands, tasks

from bot.config import Config
from bot.utils.cloudflare import CloudflareKV, CloudflareD1
from bot.utils.curseforge import get_curseforge_stats, format_number as cf_format
from bot.utils.modrinth import get_modrinth_stats, format_number as mr_format
from bot.utils.embeds import (
    create_curseforge_embed,
    create_modrinth_embed,
    create_new_feedback_embed,
)
from bot.utils.duel_logic import (
    start_webhook_server,
    build_expired_duel_embed,
    send_dm_with_fallback,
)
from bot.utils.stats_helpers import (
    fmt_diff,
    get_last_posted_duel_stats,
    get_last_posted_stats,
)
from bot.utils.dm_responses import (
    analyze_message,
    get_text_response,
    get_emoji_response,
    get_gif_response,
    is_support_message,
    get_support_embed,
    is_vagudle_message,
    get_vagudle_embed,
    get_challenge_embed,
)
from vagudle_bot.webhook_client import DMWebhookClient

import bot.commands.challenge as cmd_challenge
import bot.commands.duel as cmd_duel
import bot.commands.feedback as cmd_feedback
import bot.commands.leaderboard as cmd_leaderboard
import bot.commands.stats as cmd_stats

logger = logging.getLogger(__name__)

FEEDBACK_LOOKBACK_HOURS = 2
_STALE_DUEL_DM_BATCH = 10

_CF_STATS_TITLE = "CurseForge Stats Updated!"
_MR_STATS_TITLE = "Modrinth Stats Updated!"


class TajinHelper(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

        self.kv: CloudflareKV | None = None
        self.d1: CloudflareD1 | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self.dm_client: DMWebhookClient | None = None
        self._webhook_runner = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        logger.info("Running without proxy")

        self.kv = CloudflareKV(session=self.http_session)
        self.d1 = CloudflareD1(session=self.http_session)

        if Config.VAGUDLE_WORKER_URL and Config.VAGUDLE_WORKER_SECRET:
            self.dm_client = DMWebhookClient(
                Config.VAGUDLE_WORKER_URL, Config.VAGUDLE_WORKER_SECRET
            )
            logger.info("Vagudle bot DM webhook configured")
        else:
            logger.warning(
                "VAGUDLE_WORKER_URL or VAGUDLE_WORKER_SECRET not set — DMs will use main bot only"
            )

        self._webhook_runner = await start_webhook_server(self)

        cmd_challenge.setup(self)
        cmd_duel.setup(self)
        cmd_feedback.setup(self)
        cmd_leaderboard.setup(self)
        cmd_stats.setup(self)

        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            all_commands = list(self.tree.get_commands())
            self.tree.clear_commands(guild=None)
            for cmd in all_commands:
                self.tree.add_command(cmd, guild=guild)
                if cmd.name in (
                    "vagudle_challenge",
                    "vagudle_duel",
                    "vagudle_duel_activity",
                    "vagudle_leaderboard",
                ):
                    self.tree.add_command(cmd)
            await self.tree.sync(guild=guild)
            await self.tree.sync()
            logger.info("Synced slash commands to guild and vagudle commands globally")
        else:
            await self.tree.sync()
            logger.info("Synced slash commands globally")

        self.update_curseforge_stats.start()
        self.update_modrinth_stats.start()
        self.check_new_feedback.start()
        self.update_duel_stats.start()
        self.cleanup_stale_duels.start()

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
                        await send_dm_with_fallback(self, int(str(discord_id)), embed)
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

    @tasks.loop(time=[time(hour=h, minute=15) for h in range(0, 24, 2)])
    async def check_new_feedback(self):
        try:
            if not Config.FEEDBACK_CHANNEL_ID:
                logger.warning(
                    "check_new_feedback: FEEDBACK_CHANNEL_ID not configured, skipping"
                )
                return
            if not Config.SUPPORT_ROLE_ID:
                logger.warning(
                    "check_new_feedback: SUPPORT_ROLE_ID not configured, skipping"
                )
                return

            channel = self.get_channel(int(Config.FEEDBACK_CHANNEL_ID))
            if not isinstance(channel, discord.TextChannel):
                logger.error(
                    f"check_new_feedback: channel {Config.FEEDBACK_CHANNEL_ID} not found or not a text channel"
                )
                return

            since = await self.kv.get_last_feedback_check()
            now = datetime.now(timezone.utc)

            if since is None:
                since = now - timedelta(hours=FEEDBACK_LOOKBACK_HOURS)
                logger.info(
                    f"check_new_feedback: first run, looking back {FEEDBACK_LOOKBACK_HOURS}h to {since.isoformat()}"
                )

            new_feedbacks = await self.kv.get_new_feedbacks_since(since)
            await self.kv.store_last_feedback_check(now)

            if not new_feedbacks:
                logger.info("check_new_feedback: no new feedback since last check")
                return

            embed = create_new_feedback_embed(new_feedbacks)
            role_mention = f"<@&{Config.SUPPORT_ROLE_ID}>"

            await channel.send(content=role_mention, embed=embed)
            logger.info(
                f"check_new_feedback: posted {len(new_feedbacks)} new entries to #{channel.name}"
            )

        except Exception as e:
            logger.error(f"check_new_feedback task error: {e}")

    @check_new_feedback.before_loop
    async def before_check_new_feedback(self):
        await self.wait_until_ready()

    @tasks.loop(time=[time(hour=h, minute=30) for h in [0, 6, 12, 18]])
    async def update_curseforge_stats(self):
        logger.info("update_curseforge_stats: task fired")
        try:
            if not Config.STATS_CHANNEL_ID:
                logger.warning(
                    "update_curseforge_stats: STATS_CHANNEL_ID not configured"
                )
                return

            channel = self.get_channel(int(Config.STATS_CHANNEL_ID))
            if not isinstance(channel, discord.TextChannel):
                logger.error(
                    f"update_curseforge_stats: channel {Config.STATS_CHANNEL_ID} not found or not a text channel"
                )
                return

            bot_user = self.user
            if not bot_user:
                return

            stats = await get_curseforge_stats("king_tajin")

            if not stats:
                logger.warning(
                    "update_curseforge_stats: no stats or STATS_CHANNEL_ID not configured"
                )
                return

            last_stats = await get_last_posted_stats(
                channel, bot_user, _CF_STATS_TITLE
            )

            if stats["followers"] is None:
                fallback = last_stats.get("followers", 0) if last_stats else 0
                logger.info(
                    f"update_curseforge_stats: scraper failed, using fallback followers={fallback}"
                )
                stats["followers"] = fallback

            await self.kv.store_curseforge_stats(stats)

            should_post = False
            changes = []

            if last_stats is None:
                should_post = True
                logger.info(
                    "update_curseforge_stats: no previous post found, posting initial stats"
                )
            else:
                download_diff = stats["total_downloads"] - last_stats.get(
                    "total_downloads", 0
                )
                project_diff = stats["project_count"] - last_stats.get(
                    "project_count", 0
                )

                if download_diff != 0 or project_diff != 0:
                    should_post = True

                if download_diff != 0:
                    changes.append(f"{fmt_diff(download_diff, cf_format)} downloads")
                if project_diff != 0:
                    changes.append(f"{fmt_diff(project_diff, cf_format)} projects")

                logger.info(
                    f"update_curseforge_stats: download_diff={download_diff:+,} project_diff={project_diff:+}"
                )

            if not should_post:
                logger.info("update_curseforge_stats: no changes, skipping post")
                return

            try:
                embed = create_curseforge_embed(stats)
                embed.title = _CF_STATS_TITLE
                if changes:
                    embed.description = "Changes: " + ", ".join(changes)

                message = await channel.send(embed=embed)
                if hasattr(channel, "is_news") and channel.is_news():
                    try:
                        await message.publish()
                    except discord.HTTPException as e:
                        logger.error(
                            f"update_curseforge_stats: failed to publish message: {e}"
                        )

                logger.info(f"update_curseforge_stats: posted to #{channel.name}")
            except discord.Forbidden:
                logger.error(
                    f"update_curseforge_stats: no permission to post in #{channel.name}"
                )
            except discord.HTTPException as e:
                logger.error(f"update_curseforge_stats: HTTP error posting: {e}")
        except Exception as e:
            logger.error(f"update_curseforge_stats task error: {e}")

    @update_curseforge_stats.before_loop
    async def before_update_curseforge_stats(self):
        await self.wait_until_ready()

    @tasks.loop(time=[time(hour=h, minute=30) for h in [3, 9, 15, 21]])
    async def update_modrinth_stats(self):
        logger.info("update_modrinth_stats: task fired")
        try:
            stats = await get_modrinth_stats("King_Tajin")

            if not stats or not Config.STATS_CHANNEL_ID:
                logger.warning(
                    "update_modrinth_stats: no stats or STATS_CHANNEL_ID not configured"
                )
                return

            await self.kv.store_modrinth_stats(stats)

            channel_id = int(Config.STATS_CHANNEL_ID)
            channel = self.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                logger.error(
                    f"update_modrinth_stats: channel {channel_id} not found or not a text channel"
                )
                return

            bot_user = self.user
            if not bot_user:
                return

            last_stats = await get_last_posted_stats(
                channel, bot_user, _MR_STATS_TITLE
            )

            should_post = False
            changes = []

            if last_stats is None:
                should_post = True
                logger.info(
                    "update_modrinth_stats: no previous post found, posting initial stats"
                )
            else:
                download_diff = stats["total_downloads"] - last_stats.get(
                    "total_downloads", 0
                )
                project_diff = stats["project_count"] - last_stats.get(
                    "project_count", 0
                )
                follower_diff = stats["followers"] - last_stats.get("followers", 0)

                if download_diff != 0 or project_diff != 0 or follower_diff != 0:
                    should_post = True

                if download_diff != 0:
                    changes.append(f"{fmt_diff(download_diff, mr_format)} downloads")
                if project_diff != 0:
                    changes.append(f"{fmt_diff(project_diff, mr_format)} projects")
                if follower_diff != 0:
                    changes.append(f"{fmt_diff(follower_diff, mr_format)} followers")

                logger.info(
                    f"update_modrinth_stats: download_diff={download_diff:+,} project_diff={project_diff:+} follower_diff={follower_diff:+}"
                )

            if not should_post:
                logger.info("update_modrinth_stats: no changes, skipping post")
                return

            try:
                embed = create_modrinth_embed(stats)
                embed.title = _MR_STATS_TITLE
                if changes:
                    embed.description = "Changes: " + ", ".join(changes)

                message = await channel.send(embed=embed)
                if hasattr(channel, "is_news") and channel.is_news():
                    try:
                        await message.publish()
                    except discord.HTTPException as e:
                        logger.error(
                            f"update_modrinth_stats: failed to publish message: {e}"
                        )

                logger.info(f"update_modrinth_stats: posted to #{channel.name}")
            except discord.Forbidden:
                logger.error(
                    f"update_modrinth_stats: no permission to post in #{channel.name}"
                )
            except discord.HTTPException as e:
                logger.error(f"update_modrinth_stats: HTTP error posting: {e}")
        except Exception as e:
            logger.error(f"update_modrinth_stats task error: {e}")

    @update_modrinth_stats.before_loop
    async def before_update_modrinth_stats(self):
        await self.wait_until_ready()


def create_bot() -> TajinHelper:
    Config.validate()
    bot = TajinHelper()

    @bot.event
    async def on_ready():
        print(f"{bot.user} has connected to Discord!")
        print(f"Bot is in {len(bot.guilds)} guilds")
        print("━" * 50)

        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="Awaiting Feedback!"
            ),
        )

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        user_pinged = bot.user in message.mentions
        role_pinged = False
        if message.guild:
            role_pinged = any(
                role in message.role_mentions for role in message.guild.me.roles
            )

        if user_pinged or role_pinged:
            if is_vagudle_message(message):
                await message.reply(embed=get_vagudle_embed())
                await message.channel.send(embed=get_challenge_embed())
            else:
                await message.reply(embed=get_support_embed())
            await bot.process_commands(message)
            return

        if isinstance(message.channel, discord.DMChannel):
            logger.info(
                f"DM from {message.author} (id={message.author.id}): '{message.content[:80]}'"
            )
            if is_vagudle_message(message):
                await message.channel.send(embed=get_vagudle_embed())
                await message.channel.send(embed=get_challenge_embed())
            elif is_support_message(message):
                await message.channel.send(embed=get_support_embed())
            else:
                has_text, has_emoji, has_gif = analyze_message(message)
                parts = []
                if has_text:
                    parts.append(get_text_response())
                if has_emoji:
                    parts.append(get_emoji_response())
                if has_gif:
                    parts.append(get_gif_response())

                if parts:
                    await message.channel.send(" ".join(parts))

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
