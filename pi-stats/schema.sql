CREATE TABLE IF NOT EXISTS stats (
  id INTEGER PRIMARY KEY,
  cpu_percent REAL,
  ram_percent REAL,
  ram_used_mb INTEGER,
  ram_total_mb INTEGER,
  cpu_temp REAL,
  disk_percent REAL,
  disk_used_gb REAL,
  disk_total_gb REAL,
  net_sent_bps INTEGER,
  net_recv_bps INTEGER,
  uptime_seconds INTEGER,
  updated_at TEXT
);