// noinspection JSUnusedGlobalSymbols,JSUnresolvedReference

const DISCORD_API = "https://discord.com/api/v10";
const TIMESTAMP_TOLERANCE_SECONDS = 300;

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

async function verifySignature(body, signature, timestamp, secret) {
  if (!signature || !timestamp) return false;

  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > TIMESTAMP_TOLERANCE_SECONDS) {
    return false;
  }

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  return await crypto.subtle.verify(
    "HMAC",
    key,
    hexToBytes(signature),
    encoder.encode(timestamp + body)
  );
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function createDMChannel(userId, botToken) {
  const res = await fetch(`${DISCORD_API}/users/@me/channels`, {
    method: "POST",
    headers: {
      Authorization: `Bot ${botToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ recipient_id: userId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Discord returned ${res.status}`);
  }

  return res.json();
}

async function sendMessage(channelId, payload, botToken) {
  const res = await fetch(`${DISCORD_API}/channels/${channelId}/messages`, {
    method: "POST",
    headers: {
      Authorization: `Bot ${botToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Discord returned ${res.status}`);
  }

  return res.json();
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return jsonResponse({ error: "Method not allowed" }, 405);
    }

    const url = new URL(request.url);
    if (url.pathname !== "/dm") {
      return jsonResponse({ error: "Not found" }, 404);
    }

    const rawBody = await request.text();
    const signature = request.headers.get("X-Signature");
    const timestamp = request.headers.get("X-Timestamp");

    const valid = await verifySignature(rawBody, signature, timestamp, env.WEBHOOK_SECRET);
    if (!valid) {
      return jsonResponse({ error: "Invalid signature" }, 401);
    }

    let body;
    try {
      body = JSON.parse(rawBody);
    } catch {
      return jsonResponse({ error: "Invalid JSON body" }, 400);
    }

    const { user_id, content, embed } = body;

    if (!user_id) {
      return jsonResponse({ error: "Missing user_id" }, 400);
    }

    if (!content && !embed) {
      return jsonResponse({ error: "Provide at least one of: content, embed" }, 400);
    }

    const messagePayload = {};
    if (content) messagePayload.content = content;
    if (embed) messagePayload.embeds = [embed];

    try {
      const channel = await createDMChannel(String(user_id), env.BOT_TOKEN);
      await sendMessage(channel.id, messagePayload, env.BOT_TOKEN);
      return jsonResponse({ success: true });
    } catch (err) {
      return jsonResponse({ success: false, error: err.message });
    }
  },
};
