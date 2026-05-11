DROP TABLE IF EXISTS stats;
DROP TABLE IF EXISTS logs;

CREATE TABLE stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT,
  unit TEXT,
  priority INTEGER,
  message TEXT
);