import discord
from datetime import datetime, timedelta, timezone

VAGUDLE_ICON = "<:favicon:1536064871202820198>"


def create_feedback_embed(feedback: dict) -> discord.Embed:
    sentiment = feedback.get("sentiment", "unknown")
    category = feedback.get("category", "uncategorized")
    completed = feedback.get("completed", False)

    color = discord.Color.green() if completed else discord.Color.orange()

    try:
        timestamp = datetime.fromisoformat(
            feedback.get("submittedAt", "").replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        timestamp = datetime.now(timezone.utc)

    status_text = "Completed" if completed else "Pending"
    embed = discord.Embed(
        title=f"Feedback Details - {status_text}", color=color, timestamp=timestamp
    )

    message = feedback.get("message", "No message provided")
    truncated = (message[:4000] + "…") if len(message) > 4000 else message
    embed.description = f"```{truncated}```"

    embed.add_field(name="Sentiment", value=sentiment.title(), inline=True)
    embed.add_field(name="Category", value=category.title(), inline=True)
    embed.add_field(
        name="Status", value="✓ Completed" if completed else "Pending", inline=True
    )

    if feedback.get("article"):
        embed.add_field(name="Article", value=feedback.get("article"), inline=True)

    if feedback.get("website"):
        embed.add_field(name="Website", value=feedback.get("website"), inline=True)

    if feedback.get("email"):
        embed.add_field(name="Email", value=feedback["email"], inline=True)

    tags = feedback.get("tags", [])
    if tags:
        tags_str = ", ".join(f"`{tag}`" for tag in tags)
        embed.add_field(name="Tags", value=tags_str, inline=False)

    embed.add_field(
        name="Feedback ID", value=f"`{feedback.get('id', 'unknown')}`", inline=False
    )

    if feedback.get("categoryId"):
        embed.add_field(
            name="Category ID", value=f"`{feedback['categoryId']}`", inline=True
        )

    footer_text = f"IP: {feedback.get('ip', 'unknown')}"
    if feedback.get("userAgent"):
        user_agent = (
            feedback["userAgent"][:50] + "..."
            if len(feedback["userAgent"]) > 50
            else feedback["userAgent"]
        )
        footer_text += f" | {user_agent}"

    embed.set_footer(text=footer_text)

    return embed


def create_feedback_list_embed(feedbacks: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"Feedback List ({len(feedbacks)} entries)",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )

    if not feedbacks:
        embed.description = "No feedback entries found."
        return embed

    feedbacks_sorted = sorted(
        feedbacks, key=lambda x: x.get("submittedAt", ""), reverse=True
    )

    entries = []
    for feedback in feedbacks_sorted:
        feedback_id = feedback.get("id", "unknown")
        submitted_at = feedback.get("submittedAt", "")
        completed = feedback.get("completed", False)

        try:
            dt = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            date_str = "Unknown"

        status = "✅" if completed else "⭕"
        entries.append(f"{status} `{feedback_id}` - {date_str}")

    description = "\n".join(entries)

    if len(description) > 4000:
        entries_truncated = entries[:50]
        description = "\n".join(entries_truncated)
        description += f"\n\n... and {len(feedbacks) - 50} more entries"

    embed.description = description
    embed.set_footer(
        text="Use /view_feedback <id> to view details | ✅ completed ⭕ pending"
    )

    return embed


def create_new_feedback_embed(feedbacks: list) -> discord.Embed:
    count = len(feedbacks)

    embed = discord.Embed(
        title=f"🔔 {count} New Feedback {'Entry' if count == 1 else 'Entries'}",
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc),
    )

    sentiment_icons = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}

    lines = []
    for f in feedbacks:
        fid = f.get("id", "unknown")
        sentiment = f.get("sentiment", "neutral")
        category = f.get("category", "uncategorized")
        message = f.get("message", "")
        preview = (message[:60] + "…") if len(message) > 60 else message
        icon = sentiment_icons.get(sentiment, "⚪")

        try:
            dt = datetime.fromisoformat(f.get("submittedAt", "").replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M UTC")
        except (ValueError, AttributeError):
            time_str = "??:??"

        lines.append(f"{icon} `{fid}` · {category.title()} · {time_str}\n> {preview}")

    embed.description = "\n\n".join(lines)
    embed.set_footer(text="Use /view_feedback <id> for full details")

    return embed


def create_stats_embed(feedbacks: list) -> discord.Embed:
    total = len(feedbacks)
    sentiments = {"positive": 0, "negative": 0, "neutral": 0}
    categories = {}

    for f in feedbacks:
        sent = f.get("sentiment", "neutral")
        sentiments[sent] = sentiments.get(sent, 0) + 1

        cat = f.get("category", "uncategorized")
        categories[cat] = categories.get(cat, 0) + 1

    embed = discord.Embed(
        title="Feedback Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="Total Feedback", value=f"**{total}**", inline=False)

    sentiment_text = "\n".join(
        [
            f"{k.title()}: **{v}** ({v / total * 100:.1f}%)"
            for k, v in sentiments.items()
            if v > 0
        ]
    )
    embed.add_field(name="Sentiments", value=sentiment_text, inline=False)

    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
    category_text = "\n".join([f"{k.title()}: **{v}**" for k, v in top_categories])
    embed.add_field(name="Top Categories", value=category_text, inline=False)

    return embed


def create_order_embed(total: str | None, items: list) -> discord.Embed:
    embed = discord.Embed(
        title="🛒 New Order!",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc),
    )

    if items:
        lines = [
            f"**{item.get('quantity', 1)}x** {item.get('name', 'Item')}"
            for item in items
        ]
        embed.add_field(name="Items", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Items", value="No item details provided", inline=False)

    embed.add_field(
        name="Total", value=f"**{total}**" if total else "Unknown", inline=False
    )
    embed.set_footer(text="Thank you for all the support!")

    return embed


_STATUS_EMOJI = {"correct": "🟩", "present": "🟨", "absent": "⬛"}
_VAGUDLE_COLOR = discord.Color.from_rgb(80, 0, 170)


def render_guess_row(statuses: list[str]) -> str:
    return "".join(_STATUS_EMOJI.get(s, "⬛") for s in statuses)


def render_masked_guessed_row(word_length: int) -> str:
    return "❔" * word_length


def render_masked_empty_row(word_length: int) -> str:
    return "⬜" * word_length


def build_daily_progress_embed(
    daily_number: int,
    date_str: str,
    word_length: int,
    max_guesses: int,
    players: dict,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{VAGUDLE_ICON} Vagudle Daily #{daily_number}",
        description=f"📅 {date_str}",
        color=_VAGUDLE_COLOR,
        timestamp=datetime.now(timezone.utc),
    )

    if not players:
        embed.add_field(
            name="Players", value="Waiting for someone to start...", inline=False
        )
        return embed

    lines = []
    for player in players.values():
        mention = f"<@{player['discord_id']}>"

        if player.get("finished"):
            header = (
                f"✅ {mention} — Won in {player.get('guesses_used', '?')}"
                if player.get("won")
                else f"❌ {mention} — Lost"
            )
            grid_rows = [render_guess_row(row) for row in player.get("grid", [])]
            lines.append("\n".join([header, *grid_rows]))
            continue

        guessed = player.get("guess_count", 0)
        remaining = max(0, max_guesses - guessed)
        rows = [render_masked_guessed_row(word_length) for _ in range(guessed)]
        rows.extend(render_masked_empty_row(word_length) for _ in range(remaining))
        lines.append(f"{mention}\n" + "\n".join(rows))

    embed.add_field(
        name="Today's players", value="\n\n".join(lines)[:1024], inline=False
    )
    return embed


def add_group_streak_footer(embed: discord.Embed, streak: dict | None) -> None:
    if not streak:
        return
    current = streak.get("current_streak", 0)
    best = streak.get("best_streak", 0)
    embed.set_footer(text=f"🔥 Group streak: {current} (best: {best})")


def build_daily_reminder_embed(daily_number: int, date_str: str) -> discord.Embed:
    reset_at = datetime.strptime(date_str, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    ) + timedelta(days=1, hours=8)
    reset_ts = int(reset_at.timestamp())

    embed = discord.Embed(
        title=f"{VAGUDLE_ICON} Vagudle Daily #{daily_number}",
        description=(
            f"No one's played today's daily yet, get a game in before it resets "
            f"<t:{reset_ts}:R>!"
        ),
        color=_VAGUDLE_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"📅 {date_str}")
    return embed


def create_curseforge_embed(stats: dict) -> discord.Embed:
    from bot.utils.curseforge import format_number

    embed = discord.Embed(
        title=f"CurseForge Stats - {stats['username']}",
        color=discord.Color.from_rgb(240, 84, 44),
        url=f"https://www.curseforge.com/members/{stats['username']}/projects",
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="Followers", value=f"**{format_number(stats['followers'])}**", inline=True
    )
    embed.add_field(name="Projects", value=f"**{stats['project_count']}**", inline=True)
    embed.add_field(
        name="Total Downloads",
        value=f"**{format_number(stats['total_downloads'])}**",
        inline=True,
    )
    embed.set_footer(text="Data from CurseForge API")

    return embed


def create_modrinth_embed(stats: dict) -> discord.Embed:
    from bot.utils.modrinth import format_number

    embed = discord.Embed(
        title=f"Modrinth Stats - {stats['username']}",
        color=discord.Color.from_rgb(30, 175, 115),
        url=f"https://modrinth.com/user/{stats['username']}",
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="Followers", value=f"**{format_number(stats['followers'])}**", inline=True
    )
    embed.add_field(name="Projects", value=f"**{stats['project_count']}**", inline=True)
    embed.add_field(
        name="Total Downloads",
        value=f"**{format_number(stats['total_downloads'])}**",
        inline=True,
    )
    embed.set_footer(text="Data from Modrinth API")

    return embed
