import aiohttp
import logging

logger = logging.getLogger(__name__)


async def get_modrinth_stats(username):
    base_url = "https://api.modrinth.com/v2"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/user/{username}", timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"Modrinth API returned status {response.status}")
                    return None

                user_data = await response.json()
                user_id = user_data['id']

            async with session.get(f"{base_url}/user/{user_id}/projects",
                                   timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"Modrinth projects API returned status {response.status}")
                    return None

                projects = await response.json()

            total_downloads = sum(project.get('downloads', 0) for project in projects)
            total_followers = sum(project.get('followers', 0) for project in projects)

            mods = sorted([
                {
                    'name': project.get('title', 'Unknown'),
                    'downloads': project.get('downloads', 0),
                    'url': f"https://modrinth.com/project/{project.get('slug', project.get('id', ''))}"
                }
                for project in projects
            ], key=lambda m: m['downloads'], reverse=True)

            stats = {
                'username': username,
                'followers': total_followers,
                'project_count': len(projects),
                'total_downloads': total_downloads,
                'mods': mods
            }

            logger.info(
                f"Modrinth stats for {username}: Projects={stats['project_count']}, Downloads={stats['total_downloads']}, Followers={stats['followers']}")
            return stats

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching Modrinth data: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching Modrinth data: {e}")
        return None


def format_number(num: int) -> str:
    return "{:,}".format(num)