from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .config import AppConfig, save_monitors

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class ConfigManager:
    """Thread-safe centralized config holder with live update support."""

    def __init__(self, config: AppConfig, state_dir: str | Path) -> None:
        self._config = config
        self._state_dir = Path(state_dir)
        self._lock = asyncio.Lock()
        self._scheduler: AsyncIOScheduler | None = None

    @property
    def config(self) -> AppConfig:
        return self._config

    def set_scheduler(self, scheduler: AsyncIOScheduler) -> None:
        self._scheduler = scheduler

    async def update(self, raw_dict: dict) -> AppConfig:
        """Validate, swap config, save monitors to disk, and reschedule jobs if needed."""
        async with self._lock:
            new_config = AppConfig(**raw_dict)
            old_config = self._config
            self._config = new_config
            save_monitors(new_config, self._state_dir)
            logger.info("Config updated, monitors saved to %s/monitors.yaml", self._state_dir)

            if self._scheduler:
                self._reschedule_if_changed(old_config, new_config)

            return new_config

    def _reschedule_if_changed(
        self, old: AppConfig, new: AppConfig
    ) -> None:
        jobs = {
            "price_monitor": (
                old.price_monitor.interval_seconds,
                new.price_monitor.interval_seconds,
            ),
            "position_changes": (
                old.position_changes.interval_seconds,
                new.position_changes.interval_seconds,
            ),
            "account_tracker": (
                old.account_tracker.interval_seconds,
                new.account_tracker.interval_seconds,
            ),
        }
        assert self._scheduler is not None
        for job_id, (old_interval, new_interval) in jobs.items():
            if old_interval == new_interval:
                continue
            job = self._scheduler.get_job(job_id)
            if job is None:
                continue
            job.reschedule(trigger="interval", seconds=new_interval)
            logger.info(
                "Rescheduled %s: %ds → %ds", job_id, old_interval, new_interval
            )
