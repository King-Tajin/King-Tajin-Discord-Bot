import asyncio
import logging
from bot.main import create_bot
from bot.config import Config
from vagudle_bot.main import start as start_vagudle_bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_main_bot():
    try:
        bot = create_bot()
        logger.info("Starting main bot...")
        await bot.start(Config.DISCORD_BOT_TOKEN)
    except ValueError as e:
        logger.error(f"Main bot configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Main bot error: {e}")
        raise


async def run_vagudle_bot():
    try:
        logger.info("Starting vagudle bot...")
        await start_vagudle_bot()
    except ValueError as e:
        logger.error(f"Vagudle bot configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Vagudle bot error: {e}")
        raise


async def main():
    await asyncio.gather(
        run_main_bot(),
        run_vagudle_bot(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bots stopped by user")