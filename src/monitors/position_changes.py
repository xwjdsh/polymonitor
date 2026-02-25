from __future__ import annotations

import logging

from ..config import PositionChangesConfig
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
        config: PositionChangesConfig,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._wallets = wallets
        self._config = config
        # token_id -> (title, outcome, last_value, size)
        self._last_snapshot: dict[str, tuple[str, str, float, float]] = {}

    def export_state(self) -> dict[str, tuple[str, str, float, float]]:
        return dict(self._last_snapshot)

    def import_state(self, last_snapshot: dict[str, tuple[str, str, float, float]]) -> None:
        self._last_snapshot = last_snapshot

    async def tick(self) -> None:
        for wallet in self._wallets:
            try:
                await self._check_wallet(wallet)
            except Exception:
                logger.exception("Position changes error for wallet %s", wallet)

    async def _check_wallet(self, wallet: str) -> None:
        positions = await self._client.get_positions(wallet)
        logger.info("Position changes: checking %d positions", len(positions))

        current_ids: set[str] = set()
        # (abs_change, line) tuples for sorting
        entries: list[tuple[float, str]] = []
        total_change = 0.0

        for pos in positions:
            if not pos.token_id:
                continue
            current_ids.add(pos.token_id)
            value = pos.current_value
            size = pos.size
            prev = self._last_snapshot.get(pos.token_id)

            if prev is not None:
                _, _, prev_value, prev_size = prev
                if prev_size > 0 and size != prev_size:
                    logger.debug(
                        "Skipping %s [%s]: quantity changed %.4f → %.4f (buy/sell)",
                        pos.title, pos.outcome, prev_size, size,
                    )
                    self._last_snapshot[pos.token_id] = (pos.title, pos.outcome, value, size)
                    continue
                change = value - prev_value
                threshold = self._config.default_threshold
                market_config = self._config.per_market.get(pos.condition_id)
                if market_config and market_config.threshold is not None:
                    threshold = market_config.threshold
                if abs(change) > threshold:
                    total_change += change
                    entries.append((
                        abs(change),
                        f"• {pos.title} [{pos.outcome}]\n"
                        f"  ${prev_value:.2f} → ${value:.2f} ({change:+.2f})",
                    ))

            self._last_snapshot[pos.token_id] = (pos.title, pos.outcome, value, size)

        # Detect closed positions
        for token_id, (title, outcome, prev_value, _) in list(self._last_snapshot.items()):
            if token_id not in current_ids:
                entries.append((
                    prev_value,
                    f"• {title} [{outcome}]\n"
                    f"  ${prev_value:.2f} → CLOSED",
                ))
                total_change -= prev_value
                del self._last_snapshot[token_id]

        if not entries:
            return

        # Sort by absolute change descending
        entries.sort(key=lambda e: e[0], reverse=True)
        lines = [line for _, line in entries]

        header = f"📋 <b>Position Changes</b>\n<code>{wallet[:10]}...</code>\n"
        body = "\n\n".join(lines)
        footer = f"\n<b>Net change:</b> ${total_change:+.2f}"
        await self._notifier.send_html(f"{header}\n{body}\n{footer}")
