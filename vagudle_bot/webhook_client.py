import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class DMWebhookClient:
    def __init__(self, worker_url: str, secret: str):
        self.base_url = worker_url.rstrip("/")
        self.url = self.base_url + "/dm"
        self.secret = secret

    def _sign(self, body: str) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        message = (timestamp + body).encode()
        signature = hmac.new(self.secret.encode(), message, hashlib.sha256).hexdigest()
        return signature, timestamp

    async def _post(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload)
        signature, timestamp = self._sign(body)

        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.post(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                    "X-Timestamp": timestamp,
                },
            ) as response:
                status = response.status
                try:
                    data = await response.json(content_type=None)
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                    raw = await response.text()
                    logger.warning(
                        f"DMWebhookClient: non-JSON response (status={status}): {raw[:200]} — {e}"
                    )
                    return {
                        "success": False,
                        "error": f"non-JSON response (status={status})",
                    }

                if status not in (200, 201):
                    logger.warning(
                        f"DMWebhookClient: unexpected status {status} for {url}: {data}"
                    )

                return data

    async def send_dm(
        self,
        user_id: int | str,
        content: Optional[str] = None,
        embed: Optional[dict] = None,
    ) -> dict:
        if not content and not embed:
            raise ValueError("Provide at least one of: content, embed")

        payload: dict = {"user_id": str(user_id)}
        if content:
            payload["content"] = content
        if embed:
            payload["embed"] = embed

        return await self._post(self.url, payload)

    async def send_channel_message(
        self,
        channel_id: int | str,
        content: Optional[str] = None,
        embed: Optional[dict] = None,
    ) -> dict:
        if not content and not embed:
            raise ValueError("Provide at least one of: content, embed")

        payload: dict = {"channel_id": str(channel_id)}
        if content:
            payload["content"] = content
        if embed:
            payload["embed"] = embed

        return await self._post(f"{self.base_url}/channel-message", payload)

    async def edit_channel_message(
        self,
        channel_id: int | str,
        message_id: int | str,
        content: Optional[str] = None,
        embed: Optional[dict] = None,
    ) -> dict:
        if not content and not embed:
            raise ValueError("Provide at least one of: content, embed")

        payload: dict = {"channel_id": str(channel_id), "message_id": str(message_id)}
        if content:
            payload["content"] = content
        if embed:
            payload["embed"] = embed

        return await self._post(f"{self.base_url}/channel-message/edit", payload)
