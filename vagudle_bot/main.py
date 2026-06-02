import asyncio
import logging
import discord
from bot.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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


async def main():
    Config.validate()
    async with client:
        await client.start(Config.BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
