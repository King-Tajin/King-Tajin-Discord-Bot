import asyncio
import json
import math
import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional
import logging
from datetime import time, datetime, timezone, timedelta
import aiohttp
from aiohttp import web
from bot.config import Config
from bot.utils.cloudflare import CloudflareKV, CloudflareD1, D1_TABLE_LEADERBOARD_NORMAL, D1_TABLE_LEADERBOARD_HARD
from bot.utils.embeds import create_feedback_embed, create_feedback_list_embed, create_stats_embed, \
    create_curseforge_embed, create_modrinth_embed, create_new_feedback_embed
from bot.utils.curseforge import get_curseforge_stats, format_number as cf_format
from bot.utils.modrinth import get_modrinth_stats, format_number as mr_format
from bot.utils.dm_responses import analyze_message, get_text_response, get_emoji_response, get_gif_response, \
    is_support_message, get_support_embed, is_vagudle_message, get_vagudle_embed, get_challenge_embed
from bot.utils.challenge import (
    encode_challenge, build_challenge_url, is_word_in_dict, get_dict_hints,
    DICT_LABELS, DICT_DESCRIPTIONS, ChallengeDict,
)
from bot.utils.duel import (
    get_random_word, encode_duel, build_duel_url, generate_duel_id,
    DIFFICULTY_LABELS, DIFFICULTY_CONFIG, DuelDifficulty,
)

logger = logging.getLogger(__name__)

FEEDBACK_LOOKBACK_HOURS = 2

_processed_duels: set[str] = set()


def _fmt_diff(diff: int, format_fn) -> str:
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{format_fn(diff)}"


async def _check_guild(interaction: discord.Interaction) -> bool:
    if not Config.GUILD_ID:
        return True
    if not interaction.guild or interaction.guild.id != int(Config.GUILD_ID):
        await interaction.response.send_message("This command is not available here.", ephemeral=True)
        return False
    return True


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

    r1_time = _calc_duration_seconds(r1.get("generated_at", ""), r1.get("completed_at", ""))
    r2_time = _calc_duration_seconds(r2.get("generated_at", ""), r2.get("completed_at", ""))

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


async def check_duel_completion(bot: "FeedbackBot", duel_id: str) -> None:
    if duel_id in _processed_duels:
        logger.debug(f"check_duel_completion: duel {duel_id} already processed, skipping")
        return

    results = await bot.d1.get_duel_results(duel_id)

    if len(results) < 2:
        logger.info(f"check_duel_completion: duel {duel_id} only has {len(results)} result(s), waiting for both players")
        return

    _processed_duels.add(duel_id)
    logger.info(f"check_duel_completion: duel {duel_id} complete, processing outcomes")

    r1 = results[0]
    r2 = results[1]

    dict_type = r1.get("dict_type", "normal")
    leaderboard_table = D1_TABLE_LEADERBOARD_NORMAL if dict_type == "normal" else D1_TABLE_LEADERBOARD_HARD

    r1_duel_won, r2_duel_won = _determine_duel_outcomes(r1, r2)
    r1_id = str(r1["discord_id"])
    r2_id = str(r2["discord_id"])

    lb1_ok = await bot.d1.upsert_leaderboard(r1_id, r2_id, r1_duel_won, leaderboard_table)
    lb2_ok = await bot.d1.upsert_leaderboard(r2_id, r1_id, r2_duel_won, leaderboard_table)

    if not lb1_ok or not lb2_ok:
        logger.error(f"check_duel_completion: leaderboard upsert failed for duel {duel_id}, will retry on next webhook call")
        return

    _processed_duels.add(duel_id)
    logger.info(f"check_duel_completion: leaderboard updated for duel {duel_id}")

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

        my_time = _format_duration(result.get("generated_at", ""), result.get("completed_at", ""))
        opp_time = _format_duration(opponent.get("generated_at", ""), opponent.get("completed_at", ""))

        guesses_label = f"{guesses} guess{'es' if guesses != 1 else ''}"
        opp_guesses_label = f"{opp_guesses} guess{'es' if opp_guesses != 1 else ''}" if opp_got_word else "DNF"

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
        embed.add_field(name="Opponent guesses", value=opp_guesses_label, inline=True)
        embed.add_field(name="Opponent time", value=opp_time, inline=True)

        if discord_id is None:
            logger.warning("check_duel_completion: result missing discord_id, skipping DM")
            continue

        try:
            user = await bot.fetch_user(int(str(discord_id)))
            await user.send(embed=embed)
            logger.info(f"check_duel_completion: DMed result to user {discord_id}")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"check_duel_completion: could not DM user {discord_id}: {e}")

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

    bot: FeedbackBot = request.app["bot"]
    asyncio.create_task(check_duel_completion(bot, duel_id))

    logger.info(f"handle_duel_webhook: queued completion check for duel {duel_id}")
    return web.Response(status=200)


async def start_webhook_server(bot: "FeedbackBot") -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/webhook/duel", handle_duel_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.DUEL_WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server listening on port {Config.DUEL_WEBHOOK_PORT}")
    return runner


def _build_duel_invite_embed(
    challenger: discord.User | discord.Member,
    difficulty: str,
    word_length: int,
    opponent_name: str | None = None,
) -> discord.Embed:
    guesses = DIFFICULTY_CONFIG[difficulty]["guesses"]
    diff_label = DIFFICULTY_LABELS[difficulty]

    if opponent_name:
        description = f"**{challenger.display_name}** is challenging **{opponent_name}** to a Vagudle duel!"
    else:
        description = f"**{challenger.display_name}** has issued a Vagudle duel challenge!"

    embed = discord.Embed(
        title="⚔️ Vagudle Duel Challenge!",
        description=description,
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Difficulty", value=diff_label, inline=True)
    embed.add_field(name="Word Length", value=f"{word_length} letters", inline=True)
    embed.add_field(name="Guesses", value=str(guesses), inline=True)
    embed.set_footer(text="Results won't affect your stats. Links expire in 24 hours.")
    return embed


class DuelInviteView(discord.ui.View):
    def __init__(
        self,
        player1_id: int,
        player2_id: int | None,
        word: str,
        difficulty: DuelDifficulty,
        duel_id: str,
    ):
        super().__init__(timeout=300)
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.word = word
        self.difficulty = difficulty
        self.duel_id = duel_id
        self.player1_accepted = False
        self.player2_accepted = False
        self._lock = asyncio.Lock()

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error(f"DuelInviteView error: {error}")
        try:
            await interaction.response.send_message("Something went wrong. Please try again.", ephemeral=True)
        except discord.HTTPException:
            pass

    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except (discord.HTTPException, AttributeError) as e:
            logger.warning(f"DuelInviteView: could not disable buttons: {e}")
        self.stop()

    @discord.ui.button(label="Get My Link", style=discord.ButtonStyle.primary)
    async def player1_btn(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if interaction.user.id != self.player1_id:
            await interaction.response.send_message("Only the challenger can use this button.", ephemeral=True)
            return

        async with self._lock:
            if self.player1_accepted:
                await interaction.response.send_message("You've already generated your link.", ephemeral=True)
                return
            self.player1_accepted = True

        encoded = encode_duel(self.word, self.difficulty, self.duel_id, str(self.player1_id))
        url = build_duel_url(Config.VAGUDLE_URL, encoded)
        generated_at = datetime.now(timezone.utc).isoformat()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        await interaction.client.d1.insert_duel_stub(
            duel_id=self.duel_id,
            discord_id=str(self.player1_id),
            word=self.word,
            word_length=len(self.word),
            dict_type=cfg["dict"],
            max_guesses=cfg["guesses"],
            generated_at=generated_at,
        )

        await interaction.response.send_message(
            f"Here's your duel link — keep it private!\n{url}",
            ephemeral=True,
        )

        if self.player1_accepted and self.player2_accepted:
            await self._disable_buttons(interaction)

    @discord.ui.button(label="Accept Duel", style=discord.ButtonStyle.success)
    async def player2_btn(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if interaction.user.id == self.player1_id:
            await interaction.response.send_message("You're the challenger — use the other button.", ephemeral=True)
            return

        async with self._lock:
            if self.player2_accepted:
                await interaction.response.send_message("The duel has already been accepted.", ephemeral=True)
                return

            if self.player2_id is not None and interaction.user.id != self.player2_id:
                await interaction.response.send_message("This duel challenge is not for you.", ephemeral=True)
                return

            if self.player2_id is None:
                self.player2_id = interaction.user.id

            self.player2_accepted = True

        encoded = encode_duel(self.word, self.difficulty, self.duel_id, str(self.player2_id))
        url = build_duel_url(Config.VAGUDLE_URL, encoded)
        generated_at = datetime.now(timezone.utc).isoformat()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        await interaction.client.d1.insert_duel_stub(
            duel_id=self.duel_id,
            discord_id=str(self.player2_id),
            word=self.word,
            word_length=len(self.word),
            dict_type=cfg["dict"],
            max_guesses=cfg["guesses"],
            generated_at=generated_at,
        )

        await interaction.response.send_message(
            f"You've accepted the duel! Here's your link — keep it private!\n{url}",
            ephemeral=True,
        )

        if self.player1_accepted and self.player2_accepted:
            await self._disable_buttons(interaction)


class FeedbackBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.kv: CloudflareKV | None = None
        self.d1: CloudflareD1 | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self._webhook_runner: web.AppRunner | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        logger.info("Running without proxy")

        self.kv = CloudflareKV(session=self.http_session)
        self.d1 = CloudflareD1(session=self.http_session)

        self._webhook_runner = await start_webhook_server(self)

        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            all_commands = list(self.tree.get_commands())
            self.tree.clear_commands(guild=None)
            for cmd in all_commands:
                self.tree.add_command(cmd, guild=guild)
                if cmd.name in ("vagudle_challenge", "vagudle_duel", "vagudle_leaderboard"):
                    self.tree.add_command(cmd)
            await self.tree.sync(guild=guild)
            await self.tree.sync()
            logger.info("Synced slash commands to guild, vagudle_challenge and vagudle_duel globally")
        else:
            await self.tree.sync()
            logger.info("Synced slash commands globally")

        self.update_curseforge_stats.start()
        self.update_modrinth_stats.start()
        self.check_new_feedback.start()

    async def close(self):
        if self._webhook_runner:
            await self._webhook_runner.cleanup()
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


def _build_challenge_embed(
    word: str,
    dict_type: ChallengeDict,
    guesses_val: int,
    url: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="Share with your friends!",
        description=f"{len(word)} letters · {DICT_LABELS[dict_type]} dictionary · {guesses_val} guesses",
        color=discord.Color.from_rgb(80, 0, 170),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Challenge Link", value=url, inline=False)
    embed.set_footer(text="Results won't affect your stats.")
    return embed


class DictConfirmView(discord.ui.View):
    def __init__(
        self,
        word: str,
        selected_dict: ChallengeDict,
        easier_dict: ChallengeDict,
        guesses_val: int,
    ):
        super().__init__(timeout=60)
        self.word = word
        self.selected_dict = selected_dict
        self.easier_dict = easier_dict
        self.guesses_val = guesses_val

        self.keep_btn.label = f"Keep {DICT_LABELS[selected_dict]}"
        self.switch_btn.label = f"Switch to {DICT_LABELS[easier_dict]}"

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error(f"DictConfirmView error: {error}")
        try:
            await interaction.response.send_message("Something went wrong generating the challenge. Please try again.", ephemeral=True)
        except discord.HTTPException:
            pass

    async def _send_challenge(
        self,
        interaction: discord.Interaction,
        dict_type: ChallengeDict,
    ) -> None:
        try:
            await interaction.response.defer()
            encoded, challenge_id = encode_challenge(self.word, dict_type, self.guesses_val)
            url = build_challenge_url(Config.VAGUDLE_URL, encoded)
            logger.info(f"/vagudle_challenge (dict confirm): generated id={challenge_id} url={url}")
            embed = _build_challenge_embed(self.word, dict_type, self.guesses_val, url)
            await interaction.followup.send(embed=embed)
            self.stop()
        except Exception as e:
            logger.error(f"DictConfirmView._send_challenge error: {e}")
            try:
                await interaction.followup.send("Something went wrong generating the challenge. Please try again.", ephemeral=True)
            except discord.HTTPException:
                pass

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def keep_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._send_challenge(interaction, self.selected_dict)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def switch_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._send_challenge(interaction, self.easier_dict)


class DictSwitchView(discord.ui.View):
    def __init__(self, word: str, target_dict: ChallengeDict, guesses_val: int):
        super().__init__(timeout=60)
        self.word = word
        self.target_dict = target_dict
        self.guesses_val = guesses_val
        self.use_btn.label = f"Use {DICT_LABELS[target_dict]}"

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error(f"DictSwitchView error: {error}")
        try:
            await interaction.response.send_message("Something went wrong generating the challenge. Please try again.", ephemeral=True)
        except discord.HTTPException:
            pass

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def use_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            await interaction.response.defer()
            encoded, challenge_id = encode_challenge(self.word, self.target_dict, self.guesses_val)
            url = build_challenge_url(Config.VAGUDLE_URL, encoded)
            logger.info(f"/vagudle_challenge (dict switch): generated id={challenge_id} url={url}")
            embed = _build_challenge_embed(self.word, self.target_dict, self.guesses_val, url)
            await interaction.followup.send(embed=embed)
            self.stop()
        except Exception as e:
            logger.error(f"DictSwitchView.use_btn error: {e}")
            try:
                await interaction.followup.send("Something went wrong generating the challenge. Please try again.", ephemeral=True)
            except discord.HTTPException:
                pass


_LEADERBOARD_PAGE_SIZE = 25


def _process_leaderboard_rows(rows: list[dict]) -> list[dict]:
    processed = []
    for row in rows:
        opponents_won: list[str] = json.loads(row.get("opponents_won") or "[]")
        matches_played = int(row.get("matches_played") or 0)
        matches_won = int(row.get("matches_won") or 0)
        win_rate = (matches_won / matches_played * 100) if matches_played > 0 else 0.0
        processed.append({**row, "unique_wins": len(opponents_won), "win_rate": win_rate})
    return processed


def _sort_leaderboard(rows: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "unique":
        return sorted(rows, key=lambda r: (-r["unique_wins"], -r["win_rate"]))
    return sorted(rows, key=lambda r: (-r["matches_won"], -r["win_rate"]))


async def _resolve_usernames(bot: "FeedbackBot", discord_ids: list[str]) -> dict[str, str]:
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


def _format_leaderboard_table(rows: list[dict], usernames: dict[str, str], start_rank: int) -> str:
    header = f"{'#':>2}  {'Player':<14}  {'P':>4}  {'W':>4}  {'W%':>5}  {'UW':>4}"
    separator = "─" * len(header)
    lines = [header, separator]

    for i, row in enumerate(rows):
        rank = start_rank + i
        did = str(row.get("discord_id", ""))
        name = usernames.get(did, f"#{did[-4:]}")
        if len(name) > 14:
            name = name[:13] + "…"
        played = int(row.get("matches_played") or 0)
        wins = int(row.get("matches_won") or 0)
        win_pct = f"{row['win_rate']:.0f}%"
        uw = row["unique_wins"]
        lines.append(f"{rank:>2}  {name:<14}  {played:>4}  {wins:>4}  {win_pct:>5}  {uw:>4}")

    return "```\n" + "\n".join(lines) + "\n```"


async def _build_leaderboard_embed(
    bot: "FeedbackBot",
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
    page_rows = sorted_rows[start_idx:start_idx + _LEADERBOARD_PAGE_SIZE]

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
    embed.set_footer(text=f"{diff_label} difficulty · By {sort_label} · Page {page}/{total_pages}")

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
            embed.add_field(name=f"{name}'s stats", value="No duels played yet.", inline=False)

    return embed, total_pages


class LeaderboardView(discord.ui.View):
    def __init__(
        self,
        bot: "FeedbackBot",
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
        self.sort_btn.style = (
            discord.ButtonStyle.primary if self.sort_by == "unique" else discord.ButtonStyle.secondary
        )
        self.diff_btn.style = (
            discord.ButtonStyle.primary if self.difficulty == "hard" else discord.ButtonStyle.secondary
        )
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages

    async def _update(self, interaction: discord.Interaction) -> None:
        table = D1_TABLE_LEADERBOARD_NORMAL if self.difficulty == "normal" else D1_TABLE_LEADERBOARD_HARD
        raw_rows = await self.bot.d1.get_leaderboard(table)
        self.all_rows = _process_leaderboard_rows(raw_rows)
        embed, self.total_pages = await _build_leaderboard_embed(
            self.bot, self.all_rows, self.page, self.sort_by, self.difficulty, self.lookup_user,
        )
        self._refresh_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="By unique wins", style=discord.ButtonStyle.primary)
    async def sort_btn(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.sort_by = "total" if self.sort_by == "unique" else "unique"
        self.page = 1
        await self._update(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.page = max(1, self.page - 1)
        await self._update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.page = min(self.total_pages, self.page + 1)
        await self._update(interaction)

    @discord.ui.button(label="Hard mode", style=discord.ButtonStyle.secondary)
    async def diff_btn(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.difficulty = "hard" if self.difficulty == "normal" else "normal"
        self.page = 1
        await self._update(interaction)


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
            if is_vagudle_message(message):
                await message.reply(embed=get_vagudle_embed())
                await message.channel.send(embed=get_challenge_embed())
            else:
                await message.reply(embed=get_support_embed())
            await bot.process_commands(message)
            return

        if isinstance(message.channel, discord.DMChannel):
            logger.info(f"DM from {message.author} (id={message.author.id}): '{message.content[:80]}'")
            if is_vagudle_message(message):
                await message.channel.send(embed=get_vagudle_embed())
                await message.channel.send(embed=get_challenge_embed())
            elif is_support_message(message):
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
        if not await _check_guild(interaction):
            return
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
                    logger.error(f"/post_modrinth_stats: failed to publish message: {e}")

            await interaction.followup.send(f"Posted stats to {channel.mention}")
        except discord.Forbidden:
            await interaction.followup.send(f"No permission to post in {channel.mention}")
        except discord.HTTPException as e:
            if not interaction.is_expired():
                await interaction.followup.send(f"Error posting: {e}")

    @bot.tree.command(name="clear_commands", description="Clear duplicate slash commands")
    async def clear_commands(interaction: discord.Interaction):
        logger.info(f"/clear_commands called by {interaction.user} (id={interaction.user.id})")
        if not await _check_guild(interaction):
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        if Config.GUILD_ID:
            guild = discord.Object(id=Config.GUILD_ID)
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        await interaction.followup.send("Cleared all commands. Restart the bot to re-register them.")

    @bot.tree.command(
        name="vagudle_challenge",
        description="Create a Vagudle challenge — the dictionary only signals word popularity, not difficulty",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        word="The secret word (4–7 letters) — must exist in the chosen dictionary",
        dictionary="Which word list the challenger must guess from",
        guesses="How many attempts the challenger gets",
    )
    @app_commands.choices(
        dictionary=[
            app_commands.Choice(name="Normal — Common English words", value="normal"),
            app_commands.Choice(name="Hard — Uncommon English words", value="hard"),
            app_commands.Choice(name="Extreme — Full Scrabble dictionary", value="full"),
        ],
        guesses=[
            app_commands.Choice(name="9 guesses", value=9),
            app_commands.Choice(name="11 guesses", value=11),
        ],
    )
    async def vagudle_challenge(
        interaction: discord.Interaction,
        word: str,
        dictionary: app_commands.Choice[str],
        guesses: app_commands.Choice[int],
    ):
        logger.info(
            f"/vagudle_challenge called by {interaction.user} (id={interaction.user.id}) "
            f"— word='{word}' dict='{dictionary.value}' guesses={guesses.value}"
        )

        clean = word.upper().replace(" ", "")

        if not clean.isalpha():
            await interaction.response.send_message(
                "❌ The word can only contain letters — no spaces, numbers, or symbols.",
                ephemeral=True,
            )
            return

        if len(clean) < 4 or len(clean) > 7:
            await interaction.response.send_message(
                f"❌ `{clean}` is {len(clean)} letter{'s' if len(clean) != 1 else ''} long. Words must be 4–7 letters.",
                ephemeral=True,
            )
            return

        dict_type: ChallengeDict = dictionary.value  # type: ignore[assignment]
        hints = get_dict_hints(clean, dict_type)

        if not is_word_in_dict(clean, dict_type):
            found_in: ChallengeDict | None = hints["found_in"]
            if found_in:
                await interaction.response.send_message(
                    f"❌ `{clean}` isn't in the **{DICT_LABELS[dict_type]}** dictionary "
                    f"({DICT_DESCRIPTIONS[dict_type].lower()}).\n"
                    f"`{clean}` does appear in the **{DICT_LABELS[found_in]}** dictionary "
                    f"({DICT_DESCRIPTIONS[found_in].lower()}) though.",
                    view=DictSwitchView(clean, found_in, guesses.value),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"❌ `{clean}` isn't in the **{DICT_LABELS[dict_type]}** dictionary "
                    f"or any of the other dictionaries. Try a different word.",
                    ephemeral=True,
                )
            return

        easier_than: ChallengeDict | None = hints["easier_than"]
        if easier_than:
            logger.info(
                f"/vagudle_challenge: '{clean}' also in easier dict '{easier_than}', prompting user"
            )
            view = DictConfirmView(clean, dict_type, easier_than, guesses.value)
            await interaction.response.send_message(
                f"⚠️ Heads up: `{clean}` also appears in the **{DICT_LABELS[easier_than]}** dictionary "
                f"({DICT_DESCRIPTIONS[easier_than].lower()}).\n\n"
                f"The dictionary doesn't affect gameplay difficulty — it only tells the player how "
                f"common the word is. Choosing **{DICT_LABELS[easier_than]}** gives the player more "
                f"precise information about the word's popularity.\n\n"
                f"Which dictionary would you like to use?",
                view=view,
                ephemeral=True,
            )
            return

        encoded, challenge_id = encode_challenge(clean, dict_type, guesses.value)
        url = build_challenge_url(Config.VAGUDLE_URL, encoded)

        logger.info(f"/vagudle_challenge: generated id={challenge_id} url={url}")

        embed = _build_challenge_embed(clean, dict_type, guesses.value, url)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(
        name="vagudle_duel",
        description="Challenge someone to a Vagudle duel with a randomly chosen word",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        difficulty="Normal: 11 guesses, common words — Hard: 9 guesses, uncommon words",
        word_length="How many letters the secret word will have (4–7)",
    )
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="Normal — 11 guesses, common words", value="normal"),
            app_commands.Choice(name="Hard — 9 guesses, uncommon words", value="hard"),
        ],
        word_length=[
            app_commands.Choice(name="4 letters", value=4),
            app_commands.Choice(name="5 letters", value=5),
            app_commands.Choice(name="6 letters", value=6),
            app_commands.Choice(name="7 letters", value=7),
        ],
    )
    async def vagudle_duel(
        interaction: discord.Interaction,
        difficulty: app_commands.Choice[str],
        word_length: app_commands.Choice[int],
    ):
        logger.info(
            f"/vagudle_duel called by {interaction.user} (id={interaction.user.id}) "
            f"— difficulty='{difficulty.value}' word_length={word_length.value}"
        )

        diff: DuelDifficulty = difficulty.value  # type: ignore[assignment]

        word = get_random_word(diff, word_length.value)
        if word is None:
            await interaction.response.send_message(
                f"❌ Couldn't find a {word_length.value}-letter word for **{DIFFICULTY_LABELS[diff]}** difficulty. Try a different length.",
                ephemeral=True,
            )
            return

        player2_id: int | None = None
        opponent_name: str | None = None

        channel = interaction.channel
        if isinstance(channel, discord.DMChannel):
            recipient = getattr(channel, "recipient", None)
            if recipient is not None and recipient.id != interaction.user.id:
                player2_id = recipient.id
                opponent_name = recipient.display_name
                logger.info(f"/vagudle_duel: detected DM, pre-assigned player2={player2_id} ({opponent_name})")

        duel_id = generate_duel_id()

        view = DuelInviteView(
            player1_id=interaction.user.id,
            player2_id=player2_id,
            word=word,
            difficulty=diff,
            duel_id=duel_id,
        )

        embed = _build_duel_invite_embed(interaction.user, diff, word_length.value, opponent_name)

        await interaction.response.send_message(embed=embed, view=view)
        logger.info(f"/vagudle_duel: posted invite, duel_id={duel_id} player1={interaction.user.id} player2={player2_id}")

    @bot.tree.command(
        name="vagudle_leaderboard",
        description="View the Vagudle duel leaderboard",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="Look up a specific player's rank and stats")
    async def vagudle_leaderboard(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
    ):
        logger.info(
            f"/vagudle_leaderboard called by {interaction.user} (id={interaction.user.id}) "
            f"— lookup={'@' + str(user) if user else 'none'}"
        )
        await interaction.response.defer()

        raw_rows = await bot.d1.get_leaderboard(D1_TABLE_LEADERBOARD_NORMAL)
        all_rows = _process_leaderboard_rows(raw_rows)

        embed, total_pages = await _build_leaderboard_embed(
            bot, all_rows, 1, "unique", "normal", user,
        )

        view = LeaderboardView(
            bot=bot,
            all_rows=all_rows,
            sort_by="unique",
            difficulty="normal",
            page=1,
            total_pages=total_pages,
            lookup_user=user,
        )

        await interaction.followup.send(embed=embed, view=view)

    return bot