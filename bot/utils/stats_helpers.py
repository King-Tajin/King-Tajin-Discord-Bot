import discord
from typing import Optional


def fmt_diff(diff: int, format_fn) -> str:
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{format_fn(diff)}"


async def get_last_posted_stats(
    channel: discord.TextChannel,
    bot_user: discord.ClientUser,
    title_prefix: str,
) -> Optional[dict]:
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
                        stats["total_downloads"] = value
                    elif field.name == "Projects":
                        stats["project_count"] = value
                    elif field.name == "Followers":
                        stats["followers"] = value
                if stats:
                    return stats
    return None


async def get_last_posted_duel_stats(
    channel: discord.TextChannel,
    bot_user: discord.ClientUser,
) -> Optional[dict]:
    async for message in channel.history(limit=200):
        if message.author != bot_user:
            continue
        for embed in message.embeds:
            if embed.title and embed.title.startswith("Vagudle Duel Stats"):
                stats = {}
                for field in embed.fields:
                    raw = field.value.replace("**", "").replace(",", "").strip()
                    try:
                        value = int(raw)
                    except ValueError:
                        continue
                    if field.name == "Duels Played":
                        stats["duels_played"] = value
                if stats:
                    return stats
    return None
