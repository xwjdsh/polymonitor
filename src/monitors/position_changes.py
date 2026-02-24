from __future__ import annotations

import logging

from ..notifier import Notifier
from ..polymarket.client import PolymarketClient

logger = logging.getLogger(__name__)


class PositionChanges:
    """Periodically report position value changes since last check."""

    def __init__(
        self,
        client: PolymarketClient,
        notifier: Notifier,
        wallets: list[str],
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._wallets = wallets
        # token_id -> (title, outcome, last_value)
        self._last_snapshot: dict[str, tuple[str, str, float]] = {}

    async def tick(self) -> None:
        for wallet in self._wallets:
            try:
                await self._check_wallet(wallet)
            except Exception:
                logger.exception("Position changes error for wallet %s", wallet)

    async def _check_wallet(self, wallet: str) -> None:
        positions = await self._client.get_positions(wallet)

        current_ids: set[str] = set()
        lines: list[str] = []
        total_change = 0.0

        for pos in positions:
            if not pos.token_id:
                continue
            current_ids.add(pos.token_id)
            value = pos.current_value
            prev = self._last_snapshot.get(pos.token_id)

            if prev is not None:
                _, _, prev_value = prev
                change = value - prev_value
                if abs(change) > 0.005:
                    total_change += change
                    lines.append(
                        f"  {pos.title} [{pos.outcome}]\n"
                        f"    ${prev_value:.2f} -> ${value:.2f} ({change:+.2f})"
                    )

            self._last_snapshot[pos.token_id] = (pos.title, pos.outcome, value)

        # Detect closed positions
        for token_id, (title, outcome, prev_value) in list(self._last_snapshot.items()):
            if token_id not in current_ids:
                lines.append(
                    f"  {title} [{outcome}]\n"
                    f"    ${prev_value:.2f} -> CLOSED"
                )
                total_change -= prev_value
                del self._last_snapshot[token_id]

        if not lines:
            return

        header = f"*Position Changes*\n`{wallet[:10]}...`\n"
        body = "\n".join(lines)
        footer = f"\n*Net change:* ${total_change:+.2f}"
        await self._notifier.send(f"{header}\n{body}\n{footer}")
