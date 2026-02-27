from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..notifier import Notifier
from ..polymarket.client import PolymarketClient

if TYPE_CHECKING:
    from ..config_manager import ConfigManager

logger = logging.getLogger(__name__)


def _ts_to_int(ts: str) -> int:
    """Convert a timestamp string to an integer for reliable comparison."""
    try:
        return int(ts)
    except ValueError:
        return 0


class AccountTracker:
    """Track activities of specific accounts and alert on new actions."""

    def __init__(
        self,
        client: PolymarketClient,
        notifier: Notifier,
        config_mgr: ConfigManager,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._config_mgr = config_mgr
        # address -> last seen activity timestamp (epoch string)
        self._last_seen: dict[str, str] = {}

    def export_state(self) -> dict[str, str]:
        return dict(self._last_seen)

    def import_state(self, last_seen: dict[str, str]) -> None:
        self._last_seen = last_seen

    async def tick(self) -> None:
        """Run one tracking cycle."""
        for account in self._config_mgr.config.account_tracker.accounts:
            try:
                await self._check_account(account)
            except Exception:
                logger.exception("Account tracker error for %s", account.label)

    async def _check_account(self, account) -> None:
        since = self._last_seen.get(account.address)
        if since is None:
            # First time seeing this account — set last_seen to now (epoch)
            # so we don't flood with historical activities.
            self._last_seen[account.address] = str(int(time.time()))
            logger.info("Account tracker: initialized %s, skipping history", account.label)
            return

        activities = await self._client.get_activity(
            wallet=account.address,
            limit=50,
            start_time=since,
        )

        if not activities:
            logger.info("Account tracker: no new activity for %s", account.label)
            return

        # Filter only truly new activities (after last_seen)
        since_int = _ts_to_int(since)
        activities = [a for a in activities if _ts_to_int(a.timestamp) > since_int]

        if not activities:
            return

        # Update last seen to the most recent timestamp
        latest = max(activities, key=lambda a: _ts_to_int(a.timestamp)).timestamp
        self._last_seen[account.address] = latest

        # Group and send
        for activity in activities:
            side_emoji = "🟢 BUY" if activity.side == "BUY" else "🔴 SELL"
            msg = (
                f"👁 <b>Account Activity</b>\n\n"
                f"<b>{account.label}</b> (<code>{account.address[:10]}...</code>)\n\n"
                f"{activity.type} | {side_emoji}\n"
                f"📈 {activity.event_title}\n"
                f"{activity.title} — {activity.outcome}\n"
                f"💰 {activity.tokens:.2f} shares @ ${activity.price:.2f} (${activity.cash:.2f})\n"
                f"🕐 {activity.timestamp}"
            )
            await self._notifier.send_html(msg)
