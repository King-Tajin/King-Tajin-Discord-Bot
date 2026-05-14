import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional
import logging
from datetime import time, datetime, timezone, timedelta
import aiohttp
from bot.config import Config
from bot.utils.cloudflare import CloudflareKV
from bot.utils.embeds import create_feedback_embed, create_feedback_list_embed, create_stats_embed, \
    create_curseforge_embed, create_modrinth_embed, create_new_feedback_embed
from bot.utils.curseforge import get_curseforge_stats, format_number as cf_format
from bot.utils.modrinth import get_modrinth_stats, format_number as mr_format
from bot.utils.dm_responses import analyze_message, get_text_response, get_emoji_response, get_gif_response, \
    is_support_message, get_support_embed

logger = logging.getLogger(__name__)

FEEDBACK_LOOKBACK_HOURS = 2


def _fmt_diff(diff: int, format_fn) -> str:
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{format_fn(diff)}"


async def get_last_posted_stats(channel: discord.TextChannel, bot_user: discord.ClientUser, title_prefix: str) -> Optional[dict]:
    async for message in channel.history(limit=200):
        if message.author != bot_user:
            continue
        for embed in message.embeds:
            if embed.title and embed.title.startswith(title_prefix):
                stats = {}
                for field in embed.fields:
                    raw = field.value.replace("**", "").replace(",", "").strip()
                    try:
                        value = int(raw)
                    except ValueError:
                        continue
                    if field.name == "Total Downloads":
                        stats['total_downloads'] = value
                    elif field.name == "Projects":
                        stats['project_count'] = value
                    elif field.name == "Followers":
                        stats['followers'] = value
                if stats:
                    return stats
    return None


class FeedbackBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.kv = None
        self.http_session = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        logger.info("Running without proxy")

        self.kv = CloudflareKV(session=self.http_session)

        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced slash commands to guild")
        else:
            await self.tree.sync()
            logger.info("Synced slash commands globally")

        self.update_curseforge_stats.start()
        self.update_modrinth_stats.start()
        self.check_new_feedback.start()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def cog_unload(self):
        self.update_curseforge_stats.cancel()
        self.update_modrinth_stats.cancel()
        self.check_new_feedback.cancel()

    @tasks.loop(time=[time(hour=h, minute=15) for h in range(0, 24, 2)])
    async def check_new_feedback(self):
        try:
            if not Config.FEEDBACK_CHANNEL_ID:
                logger.warning("check_new_feedback: FEEDBACK_CHANNEL_ID not configured, skipping")
                return
            if not Config.SUPPORT_ROLE_ID:
                logger.warning("check_new_feedback: SUPPORT_ROLE_ID not configured, skipping")
                return

            channel = self.get_channel(int(Config.FEEDBACK_CHANNEL_ID))
            if not isinstance(channel, discord.TextChannel):
                logger.error(f"check_new_feedback: channel {Config.FEEDBACK_CHANNEL_ID} not found or not a text channel")
                return

            since = await self.kv.get_last_feedback_check()
            now = datetime.now(timezone.utc)

            if since is None:
                since = now - timedelta(hours=FEEDBACK_LOOKBACK_HOURS)
                logger.info(f"check_new_feedback: first run, looking back {FEEDBACK_LOOKBACK_HOURS}h to {since.isoformat()}")

            new_feedbacks = await self.kv.get_new_feedbacks_since(since)
            await self.kv.store_last_feedback_check(now)

            if not new_feedbacks:
                logger.info("check_new_feedback: no new feedback since last check")
                return

            embed = create_new_feedback_embed(new_feedbacks)
            role_mention = f"<@&{Config.SUPPORT_ROLE_ID}>"

            await channel.send(content=role_mention, embed=embed)
            logger.info(f"check_new_feedback: posted {len(new_feedbacks)} new entries to #{channel.name}")

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
                logger.warning("update_curseforge_stats: STATS_CHANNEL_ID not configured")
                return

            channel = self.get_channel(int(Config.STATS_CHANNEL_ID))
            if not isinstance(channel, discord.TextChannel):
                logger.error(f"update_curseforge_stats: channel {Config.STATS_CHANNEL_ID} not found or not a text channel")
                return

            bot_user = self.user
            if not bot_user:
                return

            stats = await get_curseforge_stats("king_tajin")

            if not stats:
                logger.warning("update_curseforge_stats: no stats or STATS_CHANNEL_ID not configured")
                return

            last_stats = await get_last_posted_stats(channel, bot_user, "CurseForge Stats")

            if stats['followers'] is None:
                fallback = last_stats.get('followers', 0) if last_stats else 0
                logger.info(f"update_curseforge_stats: scraper failed, using fallback followers={fallback}")
                stats['followers'] = fallback

            await self.kv.store_curseforge_stats(stats)

            should_post = False
            changes = []

            if last_stats is None:
                should_post = True
                logger.info("update_curseforge_stats: no previous post found, posting initial stats")
            else:
                download_diff = stats['total_downloads'] - last_stats.get('total_downloads', 0)
                project_diff = stats['project_count'] - last_stats.get('project_count', 0)

                if download_diff != 0 or project_diff != 0:
                    should_post = True

                if download_diff != 0:
                    changes.append(f"{_fmt_diff(download_diff, cf_format)} downloads")
                if project_diff != 0:
                    changes.append(f"{_fmt_diff(project_diff, cf_format)} projects")

                logger.info(f"update_curseforge_stats: download_diff={download_diff:+,} project_diff={project_diff:+}")

            if not should_post:
                logger.info("update_curseforge_stats: no changes, skipping post")
                return

            try:
                embed = create_curseforge_embed(stats)
                embed.title = "CurseForge Stats Updated!"
                if changes:
                    embed.description = "Changes: " + ", ".join(changes)

                message = await channel.send(embed=embed)
                if hasattr(channel, 'is_news') and channel.is_news():
                    try:
                        await message.publish()
                    except discord.HTTPException as e:
                        logger.error(f"update_curseforge_stats: failed to publish message: {e}")

                logger.info(f"update_curseforge_stats: posted to #{channel.name}")
            except discord.Forbidden:
                logger.error(f"update_curseforge_stats: no permission to post in #{channel.name}")
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
                logger.warning("update_modrinth_stats: no stats or STATS_CHANNEL_ID not configured")
                return

            await self.kv.store_modrinth_stats(stats)

            channel_id = int(Config.STATS_CHANNEL_ID)
            channel = self.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                logger.error(f"update_modrinth_stats: channel {channel_id} not found or not a text channel")
                return

            bot_user = self.user
            if not bot_user:
                return
            last_stats = await get_last_posted_stats(channel, bot_user, "Modrinth Stats")

            should_post = False
            changes = []

            if last_stats is None:
                should_post = True
                logger.info("update_modrinth_stats: no previous post found, posting initial stats")
            else:
                download_diff = stats['total_downloads'] - last_stats.get('total_downloads', 0)
                project_diff = stats['project_count'] - last_stats.get('project_count', 0)
                follower_diff = stats['followers'] - last_stats.get('followers', 0)

                if download_diff != 0 or project_diff != 0 or follower_diff != 0:
                    should_post = True

                if download_diff != 0:
                    changes.append(f"{_fmt_diff(download_diff, mr_format)} downloads")
                if project_diff != 0:
                    changes.append(f"{_fmt_diff(project_diff, mr_format)} projects")
                if follower_diff != 0:
                    changes.append(f"{_fmt_diff(follower_diff, mr_format)} followers")

                logger.info(f"update_modrinth_stats: download_diff={download_diff:+,} project_diff={project_diff:+} follower_diff={follower_diff:+}")

            if not should_post:
                logger.info("update_modrinth_stats: no changes, skipping post")
                return

            try:
                embed = create_modrinth_embed(stats)
                embed.title = "Modrinth Stats Updated!"
                if changes:
                    embed.description = "Changes: " + ", ".join(changes)

                message = await channel.send(embed=embed)
                if hasattr(channel, 'is_news') and channel.is_news():
                    try:
                        await message.publish()
                    except discord.HTTPException as e:
                        logger.error(f"update_modrinth_stats: failed to publish message: {e}")

                logger.info(f"update_modrinth_stats: posted to #{channel.name}")
            except discord.Forbidden:
                logger.error(f"update_modrinth_stats: no permission to post in #{channel.name}")
            except discord.HTTPException as e:
                logger.error(f"update_modrinth_stats: HTTP error posting: {e}")
        except Exception as e:
            logger.error(f"update_modrinth_stats task error: {e}")

    @update_modrinth_stats.before_loop
    async def before_update_modrinth_stats(self):
        await self.wait_until_ready()


def create_bot() -> FeedbackBot:
    Config.validate()
    bot = FeedbackBot()

    @bot.event
    async def on_ready():
        print(f'{bot.user} has connected to Discord!')
        print(f'Bot is in {len(bot.guilds)} guilds')
        print('━' * 50)

        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Awaiting Feedback!"
            )
        )

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        user_pinged = bot.user in message.mentions
        role_pinged = False
        if message.guild:
            role_pinged = any(role in message.role_mentions for role in message.guild.me.roles)

        if user_pinged or role_pinged:
            await message.reply(embed=get_support_embed())
            await bot.process_commands(message)
            return

        if isinstance(message.channel, discord.DMChannel):
            logger.info(f"DM from {message.author} (id={message.author.id}): '{message.content[:80]}'")
            if is_support_message(message):
                await message.channel.send(embed=get_support_embed())
            else:
                has_text, has_emoji, has_gif = analyze_message(message)
                parts = []
                if has_text:  parts.append(get_text_response())
                if has_emoji: parts.append(get_emoji_response())
                if has_gif:   parts.append(get_gif_response())

                if parts:
                    await message.channel.send(" ".join(parts))

        await bot.process_commands(message)

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        logger.error(f"Command error from {interaction.user} (id={interaction.user.id}): {error}")
        try:
            await interaction.followup.send("An unexpected error occurred.")
        except discord.HTTPException:
            pass

    @bot.tree.command(name="view_feedback", description="View a specific feedback by ID")
    @app_commands.describe(feedback_id="The ID of the feedback to retrieve")
    async def get_feedback(interaction: discord.Interaction, feedback_id: str):
        logger.info(f"/view_feedback called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}'")
        if not interaction.response.is_done():
            await interaction.response.defer()
        feedback = await bot.kv.get_value(feedback_id)
        if feedback:
            embed = create_feedback_embed(feedback)
            await interaction.followup.send(embed=embed)
        else:
            logger.warning(f"/view_feedback: no feedback found for id='{feedback_id}'")
            await interaction.followup.send(f"No feedback found with ID: `{feedback_id}`")

    @bot.tree.command(name="list_feedback", description="List all feedback entries")
    @app_commands.describe(sentiment="Filter by sentiment (positive, negative, neutral)", category="Filter by category")
    async def list_feedback(interaction: discord.Interaction, sentiment: Optional[str] = None,
                            category: Optional[str] = None):
        logger.info(f"/list_feedback called by {interaction.user} (id={interaction.user.id}) — sentiment={sentiment} category={category}")
        if not interaction.response.is_done():
            await interaction.response.defer()
        feedbacks = await bot.kv.get_all_feedbacks()
        if not feedbacks:
            await interaction.followup.send("No feedback entries found.")
            return
        if sentiment:
            feedbacks = [f for f in feedbacks if f.get('sentiment') == sentiment.lower()]
        if category:
            feedbacks = [f for f in feedbacks if f.get('category') == category.lower()]
        if not feedbacks:
            await interaction.followup.send("No feedback entries match your filters.")
            return
        embed = create_feedback_list_embed(feedbacks)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="feedback_stats", description="Get statistics about feedback")
    async def feedback_stats(interaction: discord.Interaction):
        logger.info(f"/feedback_stats called by {interaction.user} (id={interaction.user.id})")
        if not interaction.response.is_done():
            await interaction.response.defer()
        feedbacks = await bot.kv.get_all_feedbacks()
        if not feedbacks:
            await interaction.followup.send("No feedback entries found.")
            return
        embed = create_stats_embed(feedbacks)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="add_tag", description="Add a tag to a feedback entry")
    @app_commands.describe(feedback_id="The ID of the feedback to tag", tag="The tag to add")
    async def add_tag(interaction: discord.Interaction, feedback_id: str, tag: str):
        logger.info(f"/add_tag called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}' tag='{tag}'")
        if not interaction.response.is_done():
            await interaction.response.defer()
        success = await bot.kv.add_tag(feedback_id, tag)
        if success:
            logger.info(f"/add_tag: successfully tagged '{feedback_id}' with '{tag}'")
            await interaction.followup.send(f"Successfully added tag `{tag}` to feedback `{feedback_id}`")
        else:
            await interaction.followup.send(f"Failed to add tag. Feedback `{feedback_id}` not found.")

    @bot.tree.command(name="mark_completed", description="Mark a feedback entry as completed")
    @app_commands.describe(feedback_id="The ID of the feedback to mark as completed")
    async def mark_completed(interaction: discord.Interaction, feedback_id: str):
        logger.info(f"/mark_completed called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}'")
        if not interaction.response.is_done():
            await interaction.response.defer()
        success = await bot.kv.mark_completed(feedback_id, True)
        if success:
            logger.info(f"/mark_completed: '{feedback_id}' marked completed")
            await interaction.followup.send(f"Successfully marked feedback `{feedback_id}` as completed")
        else:
            await interaction.followup.send(f"Failed to update feedback. Feedback `{feedback_id}` not found.")

    @bot.tree.command(name="mark_pending", description="Mark a feedback entry as pending")
    @app_commands.describe(feedback_id="The ID of the feedback to mark as pending")
    async def mark_pending(interaction: discord.Interaction, feedback_id: str):
        logger.info(f"/mark_pending called by {interaction.user} (id={interaction.user.id}) — feedback_id='{feedback_id}'")
        if not interaction.response.is_done():
            await interaction.response.defer()
        success = await bot.kv.mark_completed(feedback_id, False)
        if success:
            logger.info(f"/mark_pending: '{feedback_id}' marked pending")
            await interaction.followup.send(f"Successfully marked feedback `{feedback_id}` as pending")
        else:
            await interaction.followup.send(f"Failed to update feedback. Feedback `{feedback_id}` not found.")

    @bot.tree.command(name="curseforge_stats", description="Get CurseForge statistics for king_tajin")
    async def curseforge_stats(interaction: discord.Interaction):
        logger.info(f"/curseforge_stats called by {interaction.user} (id={interaction.user.id})")
        if not interaction.response.is_done():
            await interaction.response.defer()
        stats = await get_curseforge_stats("king_tajin")
        if stats:
            if stats['followers'] is None:
                stats['followers'] = 0
            embed = create_curseforge_embed(stats)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Failed to retrieve CurseForge stats. Check bot logs for details.")

    @bot.tree.command(name="modrinth_stats", description="Get Modrinth statistics for King_Tajin")
    async def modrinth_stats(interaction: discord.Interaction):
        logger.info(f"/modrinth_stats called by {interaction.user} (id={interaction.user.id})")
        if not interaction.response.is_done():
            await interaction.response.defer()
        stats = await get_modrinth_stats("King_Tajin")
        if stats:
            embed = create_modrinth_embed(stats)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Failed to retrieve Modrinth stats. Check bot logs for details.")

    @bot.tree.command(name="post_curseforge_stats", description="Manually post CurseForge stats to the stats channel")
    async def post_curseforge_stats(interaction: discord.Interaction):
        logger.info(f"/post_curseforge_stats called by {interaction.user} (id={interaction.user.id})")
        if not interaction.response.is_done():
            await interaction.response.defer()

        if not Config.STATS_CHANNEL_ID:
            await interaction.followup.send("STATS_CHANNEL_ID not configured.")
            return

        stats = await get_curseforge_stats("king_tajin")
        if not stats:
            await interaction.followup.send("Failed to retrieve CurseForge stats.")
            return

        if stats['followers'] is None:
            stats['followers'] = 0

        channel = bot.get_channel(int(Config.STATS_CHANNEL_ID))
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(f"Channel {Config.STATS_CHANNEL_ID} not found.")
            return

        try:
            await bot.kv.store_curseforge_stats(stats)
            embed = create_curseforge_embed(stats)
            message = await channel.send(embed=embed)

            if hasattr(channel, 'is_news') and channel.is_news():
                try:
                    await message.publish()
                except discord.HTTPException as e:
                    logger.error(f"/post_curseforge_stats: failed to publish: {e}")

            await interaction.followup.send(f"Posted stats to {channel.mention}")
        except discord.Forbidden:
            await interaction.followup.send(f"No permission to post in {channel.mention}")
        except discord.HTTPException as e:
            if not interaction.is_expired():
                await interaction.followup.send(f"Error posting: {e}")

    @bot.tree.command(name="post_modrinth_stats", description="Manually post Modrinth stats to the stats channel")
    async def post_modrinth_stats(interaction: discord.Interaction):
        logger.info(f"/post_modrinth_stats called by {interaction.user} (id={interaction.user.id})")
        if not interaction.response.is_done():
            await interaction.response.defer()

        if not Config.STATS_CHANNEL_ID:
            await interaction.followup.send("STATS_CHANNEL_ID not configured.")
            return

        stats = await get_modrinth_stats("King_Tajin")
        if not stats:
            await interaction.followup.send("Failed to retrieve Modrinth stats.")
            return

        channel_id = int(Config.STATS_CHANNEL_ID)
        channel = bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(f"Channel {channel_id} not found.")
            return

        try:
            await bot.kv.store_modrinth_stats(stats)
            embed = create_modrinth_embed(stats)
            message = await channel.send(embed=embed)

            if hasattr(channel, 'is_news') and channel.is_news():
                try:
                    await message.publish()
                except discord.HTTPException as e:
                    logger.error(f"/post_modrinth_stats: failed to publish: {e}")

            await interaction.followup.send(f"Posted stats to {channel.mention}")
        except discord.Forbidden:
            await interaction.followup.send(f"No permission to post in {channel.mention}")
        except discord.HTTPException as e:
            if not interaction.is_expired():
                await interaction.followup.send(f"Error posting: {e}")

    @bot.tree.command(name="clear_commands", description="Clear duplicate slash commands")
    async def clear_commands(interaction: discord.Interaction):
        logger.info(f"/clear_commands called by {interaction.user} (id={interaction.user.id})")
        if not interaction.response.is_done():
            await interaction.response.defer()
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        await interaction.followup.send("Cleared all commands. Restart the bot to re-register them.")

    return bot