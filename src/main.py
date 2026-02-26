from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import AppConfig, load_config, load_monitors_override
from .config_manager import ConfigManager
from .notifier import Notifier
from .polymarket.client import PolymarketClient
from .monitors.price_monitor import PriceMonitor
from .monitors.position_changes import PositionChanges
from .monitors.account_tracker import AccountTracker
from .state import StateManager
from .web import init_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    overrides = load_monitors_override(config.state_dir)
    if overrides:
        merged = config.model_dump()
        for key, val in overrides.items():
            merged[key] = val
        config = AppConfig(**merged)
        logger.info("Applied monitor overrides from %s/monitors.yaml", config.state_dir)
    config_mgr = ConfigManager(config, config.state_dir)

    client = PolymarketClient()
    notifier = Notifier(config.telegram)
    state_mgr = StateManager(config.state_dir)

    # ── Init monitors ─────────────────────────────────────────
    price_monitor = PriceMonitor(
        client=client,
        notifier=notifier,
        config_mgr=config_mgr,
    )

    position_changes = PositionChanges(
        client=client,
        notifier=notifier,
        config_mgr=config_mgr,
    )

    account_tracker = AccountTracker(
        client=client,
        notifier=notifier,
        config_mgr=config_mgr,
    )

    # ── Restore state from CSV files ──────────────────────────
    pm_state = state_mgr.load_price_monitor(config.price_monitor.interval_seconds)
    if pm_state is not None:
        price_monitor.import_state(*pm_state)

    pc_state = state_mgr.load_position_changes(config.position_changes.interval_seconds)
    if pc_state is not None:
        position_changes.import_state(pc_state)

    at_state = state_mgr.load_account_tracker(config.account_tracker.interval_seconds)
    if at_state is not None:
        account_tracker.import_state(at_state)

    # ── Save state helper ─────────────────────────────────────
    def save_state() -> None:
        try:
            last_prices, triggered = price_monitor.export_state()
            state_mgr.save_price_monitor(last_prices, triggered)
        except Exception:
            logger.exception("Failed to save price monitor state")
        try:
            state_mgr.save_position_changes(position_changes.export_state())
        except Exception:
            logger.exception("Failed to save position changes state")
        try:
            state_mgr.save_account_tracker(account_tracker.export_state())
        except Exception:
            logger.exception("Failed to save account tracker state")

    # ── Schedule jobs ─────────────────────────────────────────
    scheduler = AsyncIOScheduler()
    config_mgr.set_scheduler(scheduler)

    if config.price_monitor.interval_seconds > 0:
        scheduler.add_job(
            price_monitor.tick,
            "interval",
            seconds=config.price_monitor.interval_seconds,
            id="price_monitor",
            name="Price Monitor",
        )

    if config.position_changes.interval_seconds > 0:
        scheduler.add_job(
            position_changes.tick,
            "interval",
            seconds=config.position_changes.interval_seconds,
            id="position_changes",
            name="Position Changes",
        )

    if config.account_tracker.accounts and config.account_tracker.interval_seconds > 0:
        scheduler.add_job(
            account_tracker.tick,
            "interval",
            seconds=config.account_tracker.interval_seconds,
            id="account_tracker",
            name="Account Tracker",
        )

    scheduler.add_job(
        save_state,
        "interval",
        seconds=60,
        id="save_state",
        name="Save State",
    )

    scheduler.start()
    logger.info("Polymonitor started")
    await notifier.send_html("✅ <b>Polymonitor started</b>")

    # ── First tick: fetch immediately if no prior state for that monitor ──
    if config.price_monitor.interval_seconds > 0 and pm_state is None:
        await price_monitor.tick()
        state_mgr.save_price_monitor(*price_monitor.export_state())
    if config.position_changes.interval_seconds > 0 and pc_state is None:
        await position_changes.tick()
        state_mgr.save_position_changes(position_changes.export_state())
    if config.account_tracker.accounts and config.account_tracker.interval_seconds > 0 and at_state is None:
        await account_tracker.tick()
        state_mgr.save_account_tracker(account_tracker.export_state())

    # ── Start web server ──────────────────────────────────────
    web_app = init_app(config_mgr, client)
    uvi_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=config.web_port,
        log_level="info",
    )
    server = uvicorn.Server(uvi_config)

    # ── Wait for shutdown ─────────────────────────────────────
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()
        server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        # Run web server alongside the scheduler
        server_task = asyncio.create_task(server.serve())
        await stop_event.wait()
        await server_task
    finally:
        save_state()
        scheduler.shutdown(wait=False)
        await client.close()
        logger.info("Polymonitor stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
