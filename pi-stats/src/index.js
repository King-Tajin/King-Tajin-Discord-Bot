const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Push-Secret",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method === "POST" && url.pathname === "/push") {
      return handlePush(request, env);
    }

    if (request.method === "GET" && url.pathname === "/stats") {
      return handleStats(env);
    }

    return new Response("Not Found", { status: 404 });
  },
};

async function handlePush(request, env) {
  const secret = request.headers.get("X-Push-Secret");
  if (!secret || secret !== env.PUSH_SECRET) {
    return new Response("Unauthorized", { status: 401 });
  }

  let data;
  try {
    data = await request.json();
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  await env.DB.prepare(`
    INSERT INTO stats (
      id, cpu_percent, ram_percent, ram_used_mb, ram_total_mb,
      cpu_temp, disk_percent, disk_used_gb, disk_total_gb,
      net_sent_bps, net_recv_bps, uptime_seconds, updated_at
    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      cpu_percent   = excluded.cpu_percent,
      ram_percent   = excluded.ram_percent,
      ram_used_mb   = excluded.ram_used_mb,
      ram_total_mb  = excluded.ram_total_mb,
      cpu_temp      = excluded.cpu_temp,
      disk_percent  = excluded.disk_percent,
      disk_used_gb  = excluded.disk_used_gb,
      disk_total_gb = excluded.disk_total_gb,
      net_sent_bps  = excluded.net_sent_bps,
      net_recv_bps  = excluded.net_recv_bps,
      uptime_seconds = excluded.uptime_seconds,
      updated_at    = excluded.updated_at
  `).bind(
    data.cpu_percent,
    data.ram_percent,
    data.ram_used_mb,
    data.ram_total_mb,
    data.cpu_temp ?? null,
    data.disk_percent,
    data.disk_used_gb,
    data.disk_total_gb,
    data.net_sent_bps,
    data.net_recv_bps,
    data.uptime_seconds,
    new Date().toISOString()
  ).run();

  return new Response("OK", { status: 200 });
}

async function handleStats(env) {
  const row = await env.DB.prepare("SELECT * FROM stats WHERE id = 1").first();

  if (!row) {
    return new Response(JSON.stringify({ error: "No data yet" }), {
      status: 503,
      headers: { "Content-Type": "application/json", ...CORS_HEADERS },
    });
  }

  return new Response(JSON.stringify(row), {
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}