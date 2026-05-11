from aiohttp import web
import logging
import asyncio

logger = logging.getLogger(__name__)


async def health_check(_request):
    return web.Response(text='OK', status=200)


async def keep_alive_task():
    import aiohttp
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.sleep(900)
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:10000/health', timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logger.info(f"Keep-alive ping: {resp.status}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")


async def start_health_server(port=8000):
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"Health check server running on port {port}")

    asyncio.create_task(keep_alive_task())

    return runner