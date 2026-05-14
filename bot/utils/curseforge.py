import re
import traceback
import datetime
import asyncio
import logging
import aiohttp
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, ViewportSize, Error as PlaywrightError
from bot.config import Config

logger = logging.getLogger(__name__)

BLOCKED_RESOURCES = {'image', 'stylesheet', 'font', 'media', 'other'}


def format_number(number: int) -> str:
    return "{:,}".format(number)


def parse_abbreviated_number(text: str) -> int:
    text = text.replace(',', '').strip()
    multipliers = {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}
    lower = text.lower()
    for suffix, mult in multipliers.items():
        if lower.endswith(suffix):
            return int(float(lower[:-1]) * mult)
    return int(text)


async def get_curseforge_followers(username: str) -> int | None:
    url = f"https://www.curseforge.com/members/{username}/projects"
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions',
                    '--disable-background-networking',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--mute-audio',
                    '--no-first-run',
                ]
            )

            context = await browser.new_context(
                viewport=ViewportSize(width=800, height=600),
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                java_script_enabled=True,
            )

            page = await context.new_page()

            async def handle_route(route):
                if route.request.resource_type in BLOCKED_RESOURCES:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", handle_route)

            try:
                response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)

                if not response or response.status != 200:
                    logger.warning(f"[CurseForge scraper] page returned HTTP {response.status if response else 'no response'}")
                    return None

                await page.wait_for_timeout(2000)

                text_content = await page.inner_text('body')

                match = re.search(r'([\d,]+\.?\d*[KkMmBb]?)\s+Followers?', text_content, re.IGNORECASE)
                if match:
                    count = parse_abbreviated_number(match.group(1))
                    logger.debug(f"[CurseForge scraper] found followers: {match.group(1)} → {count}")
                    return count

                logger.warning("[CurseForge scraper] follower count not found in page")
                return None
            finally:
                try:
                    await page.unroute_all(behavior='ignoreErrors')
                except PlaywrightError:
                    pass

    except PlaywrightTimeoutError:
        logger.warning("[CurseForge scraper] timed out")
        return None
    except Exception as e:
        logger.error(f"[CurseForge scraper] error: {e}\n{traceback.format_exc()}")
        return None
    finally:
        if browser:
            await browser.close()


async def get_curseforge_stats_api(username: str, session: aiohttp.ClientSession) -> dict | None:
    if not Config.CURSEFORGE_API_KEY or not Config.CURSEFORGE_AUTHOR_ID:
        logger.warning("[CurseForge API] CURSEFORGE_API_KEY or CURSEFORGE_AUTHOR_ID not configured")
        return None

    try:
        headers = {'x-api-key': Config.CURSEFORGE_API_KEY}
        total_downloads = 0
        project_count = 0
        mods = []
        page = 0

        while True:
            url = f"https://api.curseforge.com/v1/mods/search?gameId=432&authorId={Config.CURSEFORGE_AUTHOR_ID}&pageSize=50&index={page * 50}"
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.warning(f"[CurseForge API] search returned {resp.status} on page {page}")
                    return None

                data = await resp.json()

                if not data.get('data'):
                    break

                for mod in data['data']:
                    downloads = mod.get('downloadCount', 0)
                    total_downloads += downloads
                    project_count += 1
                    mods.append({
                        'name': mod.get('name', 'Unknown'),
                        'downloads': downloads,
                        'url': mod.get('links', {}).get('websiteUrl', '')
                    })

                if len(data['data']) < 50:
                    break

                page += 1

        logger.debug(f"[CurseForge API] fetched {project_count} projects across {page + 1} page(s), total downloads: {total_downloads:,}")

        mods.sort(key=lambda m: m['downloads'], reverse=True)

        current_year = datetime.datetime.now().year
        if project_count in range(current_year - 1, current_year + 2):
            logger.warning(f"[CurseForge API] project count ({project_count}) looks like a year, setting to 0")
            project_count = 0

        return {
            'username': username,
            'project_count': project_count,
            'total_downloads': total_downloads,
            'mods': mods
        }

    except aiohttp.ClientError as e:
        logger.warning(f"[CurseForge API] network error: {e}")
        return None
    except Exception as e:
        logger.error(f"[CurseForge API] unexpected error: {e}\n{traceback.format_exc()}")
        return None


async def get_curseforge_stats(username: str) -> dict | None:
    async with aiohttp.ClientSession() as session:
        api_result, followers = await asyncio.gather(
            get_curseforge_stats_api(username, session),
            get_curseforge_followers(username),
        )

    logger.info(f"[CurseForge] downloads={api_result['total_downloads'] if api_result else 'N/A'} projects={api_result['project_count'] if api_result else 'N/A'} followers={followers}")

    if not api_result or api_result['total_downloads'] == 0:
        logger.warning("[CurseForge] API returned no data")
        return None

    return {
        'username': username,
        'followers': followers,
        'project_count': api_result['project_count'],
        'total_downloads': api_result['total_downloads'],
        'mods': api_result['mods']
    }