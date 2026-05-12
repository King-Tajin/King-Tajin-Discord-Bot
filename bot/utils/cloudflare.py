import aiohttp
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict
from bot.config import Config

logger = logging.getLogger(__name__)


class CloudflareKV:
    def __init__(self, session=None):
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
                        logger.warning(f"KV get_value: invalid JSON for key '{key}'")
                        return None
                logger.warning(f"KV get_value: status {response.status} for key '{key}'")
                return None

    async def put_value(self, key: str, value: Dict) -> bool:
        url = f"{self.base_url}/values/{key}"

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=self.headers, data=json.dumps(value)) as response:
                ok = response.status in [200, 201]
                if not ok:
                    logger.warning(f"KV put_value: status {response.status} for key '{key}'")
                return ok

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[Dict]:
        url = f"{self.base_url}/keys"
        params: dict[str, int | str] = {"limit": limit}
        if prefix:
            params['prefix'] = prefix

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    keys = data.get('result', [])
                    logger.debug(f"KV list_keys: found {len(keys)} keys with prefix='{prefix}'")
                    return keys
                logger.warning(f"KV list_keys: status {response.status} for prefix='{prefix}'")
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

    async def get_last_feedback_check(self) -> Optional[datetime]:
        data = await self.get_value('_last_feedback_check')
        if not data or 'ts' not in data:
            return None
        try:
            return datetime.fromisoformat(data['ts'])
        except ValueError:
            logger.warning("KV get_last_feedback_check: invalid timestamp format")
            return None

    async def store_last_feedback_check(self, ts: datetime) -> bool:
        return await self.put_value('_last_feedback_check', {'ts': ts.isoformat()})

    async def get_new_feedbacks_since(self, since: datetime) -> List[Dict]:
        all_feedbacks = await self.get_all_feedbacks()
        new = []
        skipped = 0
        for f in all_feedbacks:
            submitted = f.get('submittedAt', '')
            if not submitted:
                skipped += 1
                continue
            try:
                dt = datetime.fromisoformat(submitted.replace('Z', '+00:00'))
                if dt > since:
                    new.append(f)
            except ValueError:
                logger.warning(f"KV get_new_feedbacks_since: unparseable timestamp '{submitted}' in feedback '{f.get('id', '?')}'")
                skipped += 1
                continue
        if skipped:
            logger.warning(f"KV get_new_feedbacks_since: skipped {skipped} entries with missing/invalid timestamps")
        return sorted(new, key=lambda x: x.get('submittedAt', ''))

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
        stats_with_timestamp = {
            **stats,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        return await self.put_value('curseforge_stats', stats_with_timestamp)

    async def store_modrinth_stats(self, stats: Dict) -> bool:
        stats_with_timestamp = {
            **stats,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        return await self.put_value('modrinth_stats', stats_with_timestamp)