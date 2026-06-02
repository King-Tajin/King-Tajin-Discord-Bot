import logging
import discord
from vagudle_bot.config import Config

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} ({client.user.id})")
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=Config.STATUS_TEXT,
        ),
    )
    logger.info("Status set")


async def start():
    Config.validate()
    async with client:
        await client.start(Config.BOT_TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(start())