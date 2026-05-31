import aiohttp
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict
from bot.config import Config

logger = logging.getLogger(__name__)

FIRST_RUN_LOOKBACK_HOURS = 2

D1_TABLE_DUEL_RESULTS = "duel_results"
D1_TABLE_LEADERBOARD_NORMAL = "leaderboard_normal"
D1_TABLE_LEADERBOARD_HARD = "leaderboard_hard"


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
                logger.warning(
                    f"KV get_value: status {response.status} for key '{key}'"
                )
                return None

    async def put_value(self, key: str, value: Dict) -> bool:
        url = f"{self.base_url}/values/{key}"

        async with aiohttp.ClientSession() as session:
            async with session.put(
                url, headers=self.headers, data=json.dumps(value)
            ) as response:
                ok = response.status in [200, 201]
                if not ok:
                    logger.warning(
                        f"KV put_value: status {response.status} for key '{key}'"
                    )
                return ok

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[Dict]:
        url = f"{self.base_url}/keys"
        params: dict[str, int | str] = {"limit": limit}
        if prefix:
            params["prefix"] = prefix

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self.headers, params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    keys = data.get("result", [])
                    logger.debug(
                        f"KV list_keys: found {len(keys)} keys with prefix='{prefix}'"
                    )
                    return keys
                logger.warning(
                    f"KV list_keys: status {response.status} for prefix='{prefix}'"
                )
                return []

    async def get_all_feedbacks(self, prefix: str = "feedback_") -> List[Dict]:
        keys = await self.list_keys(prefix=prefix)
        feedbacks = []

        for key_info in keys:
            key = key_info["name"]
            feedback = await self.get_value(key)
            if feedback:
                feedbacks.append(feedback)

        return feedbacks

    async def get_last_feedback_check(self) -> Optional[datetime]:
        data = await self.get_value("_last_feedback_check")
        if not data or "ts" not in data:
            return None
        try:
            return datetime.fromisoformat(data["ts"])
        except ValueError:
            logger.warning("KV get_last_feedback_check: invalid timestamp format")
            return None

    async def store_last_feedback_check(self, ts: datetime) -> bool:
        ok = await self.put_value("_last_feedback_check", {"ts": ts.isoformat()})
        if ok:
            logger.debug(f"KV stored last feedback check timestamp: {ts.isoformat()}")
        return ok

    async def get_new_feedbacks_since(self, since: datetime) -> List[Dict]:
        all_feedbacks = await self.get_all_feedbacks()
        logger.debug(
            f"get_new_feedbacks_since: checking {len(all_feedbacks)} total feedbacks against since={since.isoformat()}"
        )

        new = []
        skipped = 0
        for f in all_feedbacks:
            submitted = f.get("submittedAt", "")
            if not submitted:
                skipped += 1
                continue
            try:
                dt = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
                logger.debug(
                    f"  feedback '{f.get('id', '?')}' submittedAt={submitted} — {'NEW' if dt > since else 'old'}"
                )
                if dt > since:
                    new.append(f)
            except ValueError:
                logger.warning(
                    f"KV get_new_feedbacks_since: unparseable timestamp '{submitted}' in feedback '{f.get('id', '?')}'"
                )
                skipped += 1
                continue

        if skipped:
            logger.warning(
                f"KV get_new_feedbacks_since: skipped {skipped} entries with missing/invalid timestamps"
            )

        logger.info(
            f"get_new_feedbacks_since: found {len(new)} new out of {len(all_feedbacks)} total"
        )
        return sorted(new, key=lambda x: x.get("submittedAt", ""))

    async def add_tag(self, key: str, tag: str) -> bool:
        feedback = await self.get_value(key)
        if not feedback:
            return False

        if "tags" not in feedback:
            feedback["tags"] = []

        if tag not in feedback["tags"]:
            feedback["tags"].append(tag)
            return await self.put_value(key, feedback)

        return True

    async def mark_completed(self, key: str, completed: bool = True) -> bool:
        feedback = await self.get_value(key)
        if not feedback:
            return False

        feedback["completed"] = completed
        return await self.put_value(key, feedback)

    async def increment_duels_played(self) -> bool:
        current = await self.get_value("vagudle_duels_played")
        count = int(current.get("count", 0)) if current else 0
        return await self.put_value("vagudle_duels_played", {"count": count + 1})

    async def store_curseforge_stats(self, stats: Dict) -> bool:
        stats_with_timestamp = {
            **stats,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return await self.put_value("curseforge_stats", stats_with_timestamp)

    async def store_modrinth_stats(self, stats: Dict) -> bool:
        stats_with_timestamp = {
            **stats,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        return await self.put_value("modrinth_stats", stats_with_timestamp)


class CloudflareD1:
    def __init__(self, session=None):
        self.session = session
        self.account_id = Config.CLOUDFLARE_ACCOUNT_ID
        self.database_id = Config.CLOUDFLARE_D1_DATABASE_ID
        self.api_token = Config.CLOUDFLARE_API_TOKEN
        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/d1/database/{self.database_id}"
        )

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def _query(self, sql: str, params: list | None = None) -> list[dict]:
        url = f"{self.base_url}/query"
        body: dict = {"sql": sql}
        if params is not None:
            body["params"] = params

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=self._headers, json=body
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success") and data.get("result"):
                            return data["result"][0].get("results", [])
                    text = await response.text()
                    logger.warning(
                        f"D1 query failed: status={response.status} body={text[:200]}"
                    )
                    return []
        except Exception as e:
            logger.error(f"D1 query error: {e}")
            return []

    async def _execute(self, sql: str, params: list | None = None) -> bool:
        url = f"{self.base_url}/query"
        body: dict = {"sql": sql}
        if params is not None:
            body["params"] = params

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=self._headers, json=body
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return bool(data.get("success"))
                    text = await response.text()
                    logger.warning(
                        f"D1 execute failed: status={response.status} body={text[:200]}"
                    )
                    return False
        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return False

    async def insert_duel_stub(
        self,
        duel_id: str,
        discord_id: str,
        word: str,
        word_length: int,
        dict_type: str,
        max_guesses: int,
        generated_at: str,
    ) -> bool:
        return await self._execute(
            f"INSERT OR IGNORE INTO {D1_TABLE_DUEL_RESULTS} "
            f"(duel_id, discord_id, word, word_length, dict_type, max_guesses, generated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                duel_id,
                discord_id,
                word,
                word_length,
                dict_type,
                max_guesses,
                generated_at,
            ],
        )

    async def get_duel_results(self, duel_id: str) -> list[dict]:
        return await self._query(
            f"SELECT * FROM {D1_TABLE_DUEL_RESULTS} WHERE duel_id = ? AND completed_at IS NOT NULL",
            [duel_id],
        )

    async def get_stale_duel_data(self) -> list[dict]:
        return await self._query(
            f"SELECT duel_id, discord_id, completed_at, generated_at, dict_type, word "
            f"FROM {D1_TABLE_DUEL_RESULTS} "
            f"WHERE duel_id IN ("
            f"  SELECT DISTINCT duel_id FROM {D1_TABLE_DUEL_RESULTS} "
            f"  WHERE completed_at IS NULL "
            f"  AND generated_at < datetime('now', '-24 hours')"
            f")"
        )

    async def delete_stale_null_stubs(self) -> bool:
        return await self._execute(
            f"DELETE FROM {D1_TABLE_DUEL_RESULTS} "
            f"WHERE completed_at IS NULL "
            f"AND generated_at < datetime('now', '-24 hours')"
        )

    async def get_leaderboard(self, table: str) -> list[dict]:
        return await self._query(f"SELECT * FROM {table}")

    async def get_leaderboard_entry(self, discord_id: str, table: str) -> dict | None:
        rows = await self._query(
            f"SELECT * FROM {table} WHERE discord_id = ?",
            [discord_id],
        )
        return rows[0] if rows else None

    async def upsert_leaderboard(
        self,
        discord_id: str,
        opponent_id: str,
        won: bool,
        table: str,
    ) -> bool:
        current = await self.get_leaderboard_entry(discord_id, table)

        if current:
            matches_played = current["matches_played"] + 1
            matches_won = current["matches_won"] + (1 if won else 0)

            opponents_won: list[str] = json.loads(current.get("opponents_won") or "[]")
            opponents_lost: list[str] = json.loads(
                current.get("opponents_lost") or "[]"
            )

            if won:
                if opponent_id not in opponents_won:
                    opponents_won.append(opponent_id)
            else:
                if opponent_id not in opponents_lost:
                    opponents_lost.append(opponent_id)

            return await self._execute(
                f"UPDATE {table} SET matches_played = ?, matches_won = ?, opponents_won = ?, opponents_lost = ? WHERE discord_id = ?",
                [
                    matches_played,
                    matches_won,
                    json.dumps(opponents_won),
                    json.dumps(opponents_lost),
                    discord_id,
                ],
            )
        else:
            opponents_won_val = json.dumps([opponent_id] if won else [])
            opponents_lost_val = json.dumps([] if won else [opponent_id])
            return await self._execute(
                f"INSERT INTO {table} (discord_id, matches_played, matches_won, opponents_won, opponents_lost) VALUES (?, ?, ?, ?, ?)",
                [discord_id, 1, 1 if won else 0, opponents_won_val, opponents_lost_val],
            )
