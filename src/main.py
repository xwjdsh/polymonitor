from __future__ import annotations

import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import load_config
from .notifier import Notifier
from .polymarket.client import PolymarketClient
from .monitors.price_monitor import PriceMonitor
from .monitors.position_changes import PositionChanges
from .monitors.account_tracker import AccountTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    client = PolymarketClient()
    notifier = Notifier(config.telegram)

    # ── Init monitors ─────────────────────────────────────────
    price_monitor = PriceMonitor(
        client=client,
        notifier=notifier,
        wallets=config.my_wallets,
        config=config.price_monitor,
    )

    position_changes = PositionChanges(
        client=client,
        notifier=notifier,
        wallets=config.my_wallets,
    )

    account_tracker = AccountTracker(
        client=client,
        notifier=notifier,
        config=config.account_tracker,
    )

    # ── Schedule jobs ─────────────────────────────────────────
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        price_monitor.tick,
        "interval",
        seconds=config.price_monitor.interval_seconds,
        id="price_monitor",
        name="Price Monitor",
    )

    scheduler.add_job(
        position_changes.tick,
        "interval",
        seconds=config.position_changes.interval_seconds,
        id="position_changes",
        name="Position Changes",
    )

    if config.account_tracker.accounts:
        scheduler.add_job(
            account_tracker.tick,
            "interval",
            seconds=config.account_tracker.interval_seconds,
            id="account_tracker",
            name="Account Tracker",
        )

    scheduler.start()
    logger.info("Polymonitor started")
    await notifier.send("Polymonitor started")

    # ── Run first tick immediately ────────────────────────────
    await price_monitor.tick()
    if config.account_tracker.accounts:
        await account_tracker.tick()

    # ── Wait for shutdown ─────────────────────────────────────
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        await client.close()
        logger.info("Polymonitor stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
