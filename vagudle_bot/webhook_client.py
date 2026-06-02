import hashlib
import hmac
import json
import time
from typing import Optional

import aiohttp


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

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                    "X-Timestamp": timestamp,
                },
            ) as response:
                return await response.json()
