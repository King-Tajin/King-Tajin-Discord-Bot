import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timezone

import aiohttp
import psutil

from bot.config import Config

logger = logging.getLogger(__name__)

STATS_INTERVAL = 25
LOG_INTERVAL = 120

_last_log_fetch = None


def _base_worker_url() -> str:
    url = Config.WORKER_URL or ""
    return url.rstrip("/").removesuffix("/push")


def _cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except OSError:
        return None


def _collect(prev_net, prev_time):
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    now = time.monotonic()

    elapsed = (now - prev_time) if prev_time else STATS_INTERVAL
    sent_bps = int((net.bytes_sent - prev_net.bytes_sent) / elapsed) if prev_net else 0
    recv_bps = int((net.bytes_recv - prev_net.bytes_recv) / elapsed) if prev_net else 0

    return {
        "cpu_percent": cpu,
        "ram_percent": ram.percent,
        "ram_used_mb": ram.used // (1024 * 1024),
        "ram_total_mb": ram.total // (1024 * 1024),
        "cpu_temp": _cpu_temp(),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1024 ** 3, 2),
        "disk_total_gb": round(disk.total / 1024 ** 3, 2),
        "net_sent_bps": sent_bps,
        "net_recv_bps": recv_bps,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }, net, now


def _collect_logs(since: datetime) -> list[dict]:
    try:
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        result = subprocess.run(
            [
                "journalctl",
                "--since", since_str,
                "--utc",
                "--output", "json",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        entries = []
        skipped = 0
        for line in result.stdout.splitlines():
            try:
                e = json.loads(line)
                entries.append({
                    "ts": datetime.fromtimestamp(
                        int(e.get("__REALTIME_TIMESTAMP", 0)) / 1_000_000,
                        tz=timezone.utc,
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "unit": e.get("_SYSTEMD_UNIT") or e.get("SYSLOG_IDENTIFIER"),
                    "priority": int(e["PRIORITY"]) if "PRIORITY" in e else None,
                    "message": e.get("MESSAGE", ""),
                })
            except (json.JSONDecodeError, ValueError):
                skipped += 1
                continue
        if skipped:
            logger.warning(f"log collection skipped {skipped} unparseable journal lines")
        return entries
    except Exception as e:
        logger.warning(f"log collection failed: {e}")
        return []


async def run_stats_push():
    global _last_log_fetch

    prev_net = None
    prev_time = None
    last_log_push = 0
    base_url = _base_worker_url()
    push_url = f"{base_url}/push"
    logs_url = f"{base_url}/logs/push"

    logger.info(f"stats push starting — push={push_url} logs={logs_url}")

    async with aiohttp.ClientSession() as session:
        while True:
            now_wall = time.monotonic()

            try:
                payload, prev_net, prev_time = _collect(prev_net, prev_time)
                async with session.post(
                    push_url,
                    json=payload,
                    headers={"X-Push-Secret": Config.PUSH_SECRET},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        logger.debug(
                            f"stats push OK — cpu={payload['cpu_percent']}% "
                            f"ram={payload['ram_percent']}% "
                            f"temp={payload['cpu_temp']}°C"
                        )
                    else:
                        logger.warning(f"stats push returned {resp.status}")
            except aiohttp.ServerTimeoutError:
                logger.warning("stats push timed out — worker may be slow")
            except Exception as e:
                logger.warning(f"stats push failed: {e}")

            if now_wall - last_log_push >= LOG_INTERVAL:
                since = _last_log_fetch or datetime.now(tz=timezone.utc)
                _last_log_fetch = datetime.now(tz=timezone.utc)
                last_log_push = now_wall

                entries = _collect_logs(since)
                logger.debug(f"log collection: {len(entries)} entries since {since.strftime('%H:%M:%S UTC')}")

                if entries:
                    try:
                        async with session.post(
                            logs_url,
                            json=entries,
                            headers={"X-Push-Secret": Config.PUSH_SECRET},
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as resp:
                            if resp.status == 200:
                                logger.info(f"logs push OK — sent {len(entries)} entries")
                            else:
                                logger.warning(f"logs push returned {resp.status}")
                    except aiohttp.ServerTimeoutError:
                        logger.warning("logs push timed out — worker may be slow")
                    except Exception as e:
                        logger.warning(f"logs push failed: {e}")

            await asyncio.sleep(STATS_INTERVAL)