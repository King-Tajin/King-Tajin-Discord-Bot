import discord
from datetime import datetime, timedelta, timezone

VAGUDLE_ICON = "<:favicon:1536064871202820198>"

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


def get_vagudle_embed() -> discord.Embed:
    embed = discord.Embed(
        title=f"{VAGUDLE_ICON} Vagudle",
        description=(
            "A word-guessing game more challenging than Wordle: cells don't color automatically, you paint what you can figure out from the limited clues you have.\n\n"
            "**[▶ Play at vagudle.king-tajin.dev](https://vagudle.king-tajin.dev)**"
        ),
        color=0x5000AA,
    )
    embed.add_field(
        name="❓ How It Works:",
        value=(
            "Guess a word then select a brush and paint the cells based off the color counts:\n"
            "🟩 Right letter, right spot\n"
            "🟨 Right letter, wrong spot\n"
            "⬛ Letter not in the word"
        ),
        inline=False,
    )
    embed.add_field(
        name="✨ Features",
        value=(
            "• **Variable word length** — 4 through 7-letter words\n"
            "• **Unlimited games** — no daily limit\n"
            "• **Hard mode** — fewer guesses, harder words\n"
            "• **Auto-Gray / Auto-Green** — optional automation to speed up painting\n"
            "• **Row badges** — live count of green, yellow, and gray tiles per row"
        ),
        inline=False,
    )
    embed.add_field(
        name="🗓️ Daily Mode",
        value=(
            "One shared word for everyone each day — difficulty and word length change "
            "with the day of the week. Play at "
            "**[vagudle.king-tajin.dev/daily](https://vagudle.king-tajin.dev/daily)**"
        ),
        inline=False,
    )
    embed.add_field(
        name="📂 Open Source",
        value="[github.com/King-Tajin/Vagudle](https://github.com/King-Tajin/Vagudle)",
        inline=False,
    )
    embed.set_footer(text="vagudle.king-tajin.dev · King-Tajin")
    return embed


def get_challenge_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚔️ Challenge a Friend",
        description=(
            "Want to put someone to the test? Use `/vagudle_challenge` to pick a secret word "
            "and generate a custom challenge link, works in both DMs and servers!"
        ),
        color=0x5000AA,
    )
    embed.set_footer(text="Challenge results don't affect the recipient's stats.")
    return embed


def get_daily_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🗓️ Vagudle Daily",
        description=(
            "Everyone gets the same word each day. Track your group's progress and build "
            "a win streak together!\n\n"
            "**[▶ Play today's Daily](https://vagudle.king-tajin.dev/daily)**"
        ),
        color=0x5000AA,
    )
    embed.set_footer(text="A new word drops every day.")
    return embed
