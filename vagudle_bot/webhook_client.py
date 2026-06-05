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
        self.url = worker_url.rstrip("/") + "/dm"
        self.secret = secret

    def _sign(self, body: str) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        message = (timestamp + body).encode()
        signature = hmac.new(self.secret.encode(), message, hashlib.sha256).hexdigest()
        return signature, timestamp

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

        body = json.dumps(payload)
        signature, timestamp = self._sign(body)

        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.post(
                self.url,
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
                    return {"success": False, "error": f"non-JSON response (status={status})"}

                if status not in (200, 201):
                    logger.warning(
                        f"DMWebhookClient: unexpected status {status} for user {user_id}: {data}"
                    )

                return data