import asyncio
import logging
import time

import aiohttp
import psutil

from bot.config import Config

logger = logging.getLogger(__name__)

INTERVAL = 15


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

    elapsed = (now - prev_time) if prev_time else INTERVAL
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


async def run_stats_push():
    prev_net = None
    prev_time = None

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                payload, prev_net, prev_time = _collect(prev_net, prev_time)
                async with session.post(
                    Config.WORKER_URL,
                    json=payload,
                    headers={"X-Push-Secret": Config.PUSH_SECRET},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"stats push returned {resp.status}")
            except Exception as e:
                logger.warning(f"stats push failed: {e}")

            await asyncio.sleep(INTERVAL)