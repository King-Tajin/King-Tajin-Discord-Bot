import aiohttp
import json
from typing import Optional, List, Dict
from bot.config import Config


class CloudflareKV:
    def __init__(self, session=None):  # ← Add session parameter
        self.session = session
        self.account_id = Config.CLOUDFLARE_ACCOUNT_ID
        self.namespace_id = Config.CLOUDFLARE_NAMESPACE_ID
        self.api_token = Config.CLOUDFLARE_API_TOKEN
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/storage/kv/namespaces/{self.namespace_id}"

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.api_token}"}

    async def get_value(self, key: str) -> Optional[Dict]:
        url = f"{self.base_url}/values/{key}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    text = await response.text()
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return None
                return None

    async def put_value(self, key: str, value: Dict) -> bool:
        url = f"{self.base_url}/values/{key}"

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=self.headers, data=json.dumps(value)) as response:
                return response.status in [200, 201]

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[Dict]:
        url = f"{self.base_url}/keys"
        params = {"limit": limit}
        if prefix:
            params['prefix'] = prefix

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('result', [])
                return []

    async def get_all_feedbacks(self, prefix: str = "feedback_") -> List[Dict]:
        keys = await self.list_keys(prefix=prefix)
        feedbacks = []

        for key_info in keys:
            key = key_info['name']
            feedback = await self.get_value(key)
            if feedback:
                feedbacks.append(feedback)

        return feedbacks

    async def add_tag(self, key: str, tag: str) -> bool:
        feedback = await self.get_value(key)
        if not feedback:
            return False

        if 'tags' not in feedback:
            feedback['tags'] = []

        if tag not in feedback['tags']:
            feedback['tags'].append(tag)
            return await self.put_value(key, feedback)

        return True

    async def mark_completed(self, key: str, completed: bool = True) -> bool:
        feedback = await self.get_value(key)
        if not feedback:
            return False

        feedback['completed'] = completed
        return await self.put_value(key, feedback)

    async def store_curseforge_stats(self, stats: Dict) -> bool:
        from datetime import datetime, UTC

        stats_with_timestamp = {
            **stats,
            'last_updated': datetime.now(UTC).isoformat()
        }

        return await self.put_value('curseforge_stats', stats_with_timestamp)

    async def store_modrinth_stats(self, stats: Dict) -> bool:
        from datetime import datetime, UTC

        stats_with_timestamp = {
            **stats,
            'last_updated': datetime.now(UTC).isoformat()
        }

        return await self.put_value('modrinth_stats', stats_with_timestamp)