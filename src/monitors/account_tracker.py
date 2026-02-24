from __future__ import annotations

import logging
from ..config import AccountTrackerConfig, TrackedAccount
from ..notifier import Notifier
from ..polymarket.client import PolymarketClient

logger = logging.getLogger(__name__)


class AccountTracker:
    """Track activities of specific accounts and alert on new actions."""

    def __init__(
        self,
        client: PolymarketClient,
        notifier: Notifier,
        config: AccountTrackerConfig,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._accounts = config.accounts
        # address -> last seen activity timestamp (ISO string)
        self._last_seen: dict[str, str] = {}

    async def tick(self) -> None:
        """Run one tracking cycle."""
        for account in self._accounts:
            try:
                await self._check_account(account)
            except Exception:
                logger.exception("Account tracker error for %s", account.label)

    async def _check_account(self, account: TrackedAccount) -> None:
        since = self._last_seen.get(account.address)
        activities = await self._client.get_activity(
            wallet=account.address,
            limit=50,
            start_time=since,
        )

        if not activities:
            return

        # Filter only truly new activities (after last_seen)
        if since:
            activities = [a for a in activities if a.timestamp > since]

        if not activities:
            return

        # Update last seen to the most recent timestamp
        latest = max(a.timestamp for a in activities)
        self._last_seen[account.address] = latest

        # Group and send
        for activity in activities:
            side_emoji = "BUY" if activity.side == "BUY" else "SELL"
            msg = (
                f"*Account Activity*\n\n"
                f"*{account.label}* (`{account.address[:10]}...`)\n\n"
                f"Type: {activity.type} | Side: {side_emoji}\n"
                f"Market: {activity.event_title}\n"
                f"{activity.title} — {activity.outcome}\n"
                f"Amount: {activity.tokens:.2f} shares @ ${activity.price:.2f}\n"
                f"Value: ${activity.cash:.2f}\n"
                f"Time: {activity.timestamp}"
            )
            await self._notifier.send(msg)
