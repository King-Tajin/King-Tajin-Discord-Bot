const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Push-Secret, Authorization",
};

// noinspection JSUnusedGlobalSymbols
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method === "POST" && url.pathname === "/push") {
      return handleStatsPush(request, env);
    }

    if (request.method === "POST" && url.pathname === "/logs/push") {
      return handleLogsPush(request, env);
    }

    if (request.method === "GET" && url.pathname === "/stats") {
      return handleStats(env);
    }

    if (request.method === "GET" && url.pathname === "/history") {
      return handleHistory(env);
    }

    if (request.method === "GET" && url.pathname === "/logs") {
      return handleLogs(request, env);
    }

    return new Response("Not Found", { status: 404 });
  },

  async scheduled(event, env) {
    await env.DB.batch([
      env.DB.prepare(
        `DELETE FROM stats WHERE datetime(updated_at) < datetime('now', '-1 hour')`
      ),
      env.DB.prepare(
        `DELETE FROM logs WHERE datetime(ts) < datetime('now', '-12 hours')`
      ),
    ]);
  },
};

function isPushAuthed(request, env) {
  const secret = request.headers.get("X-Push-Secret");
  return secret && secret === env.PUSH_SECRET;
}

function isViewerAuthed(request, env) {
  const auth = request.headers.get("Authorization");
  if (!auth || !auth.startsWith("Bearer ")) return false;
  return auth.slice(7) === env.VIEWER_TOKEN;
}

async function handleStatsPush(request, env) {
  if (!isPushAuthed(request, env)) {
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
      cpu_percent, ram_percent, ram_used_mb, ram_total_mb,
      cpu_temp, disk_percent, disk_used_gb, disk_total_gb,
      net_sent_bps, net_recv_bps, uptime_seconds, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

async function handleLogsPush(request, env) {
  if (!isPushAuthed(request, env)) {
    return new Response("Unauthorized", { status: 401 });
  }

  let entries;
  try {
    entries = await request.json();
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  if (!Array.isArray(entries) || entries.length === 0) {
    return new Response("OK", { status: 200 });
  }

  const inserts = entries.map((e) =>
    env.DB.prepare(
      `INSERT INTO logs (ts, unit, priority, message) VALUES (?, ?, ?, ?)`
    ).bind(e.ts, e.unit ?? null, e.priority ?? null, e.message)
  );

  await env.DB.batch(inserts);

  return new Response("OK", { status: 200 });
}

async function handleStats(env) {
  const row = await env.DB.prepare(
    "SELECT * FROM stats ORDER BY id DESC LIMIT 1"
  ).first();

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

async function handleHistory(env) {
  const { results } = await env.DB.prepare(
    `SELECT * FROM stats WHERE datetime(updated_at) > datetime('now', '-1 hour') ORDER BY id ASC`
  ).all();

  return new Response(JSON.stringify(results), {
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

async function handleLogs(request, env) {
  if (!isViewerAuthed(request, env)) {
    return new Response("Unauthorized", { status: 401 });
  }

  const url = new URL(request.url);
  const unit = url.searchParams.get("unit");
  const priority = url.searchParams.get("priority");

  let query = `SELECT * FROM logs WHERE datetime(ts) > datetime('now', '-12 hours')`;
  const binds = [];

  if (unit) {
    query += " AND unit = ?";
    binds.push(unit);
  }
  if (priority !== null) {
    query += " AND priority <= ?";
    binds.push(parseInt(priority));
  }

  query += " ORDER BY id ASC";

  const { results } = await env.DB.prepare(query).bind(...binds).all();

  return new Response(JSON.stringify(results), {
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}