import asyncio
import logging
from bot.main import create_bot
from bot.config import Config
from bot.stats_push import run_stats_push

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _handle_task_exception(task: asyncio.Task):
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"stats_push task crashed: {e}", exc_info=True)


async def main():
    stats_task = None
    try:
        bot = create_bot()
        logger.info("Starting Discord bot...")
        stats_task = asyncio.create_task(run_stats_push())
        stats_task.add_done_callback(_handle_task_exception)
        await bot.start(Config.DISCORD_BOT_TOKEN)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file and ensure all required variables are set.")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise
    finally:
        if stats_task is not None:
            stats_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")