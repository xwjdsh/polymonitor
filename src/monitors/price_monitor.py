from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..notifier import Notifier
from ..polymarket.client import PolymarketClient

if TYPE_CHECKING:
    from ..config_manager import ConfigManager

logger = logging.getLogger(__name__)


class PriceMonitor:
    """Monitor position prices and alert on significant changes or level crossings."""

    def __init__(
        self,
        client: PolymarketClient,
        notifier: Notifier,
        config_mgr: ConfigManager,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._config_mgr = config_mgr
        # token_id -> last known price
        self._last_prices: dict[str, float] = {}
        # token_id -> set of alert keys already triggered (e.g. "above:0.8")
        self._triggered: dict[str, set[str]] = {}

    def export_state(self) -> tuple[dict[str, float], dict[str, set[str]]]:
        return self._last_prices.copy(), {k: set(v) for k, v in self._triggered.items()}

    def import_state(self, last_prices: dict[str, float], triggered: dict[str, set[str]]) -> None:
        self._last_prices = last_prices
        self._triggered = triggered

    async def tick(self) -> None:
        for wallet in self._config_mgr.config.my_wallets:
            try:
                await self._check_wallet(wallet)
            except Exception:
                logger.exception("Price monitor error for wallet %s", wallet)

    async def _check_wallet(self, wallet: str) -> None:
        positions = await self._client.get_positions(wallet)
        if not positions:
            return

        config = self._config_mgr.config.price_monitor
        token_count = sum(1 for p in positions if p.token_id)
        logger.info("Price monitor: fetching prices for %d tokens", token_count)

        for pos in positions:
            if not pos.token_id:
                continue

            try:
                current_price = await self._client.get_midpoint(pos.token_id)
            except Exception:
                logger.warning("Failed to get price for %s", pos.token_id)
                continue

            last_price = self._last_prices.get(pos.token_id)
            self._last_prices[pos.token_id] = current_price

            # Per-market level alerts (above/below)
            market_config = config.per_market.get(pos.condition_id)
            if market_config:
                await self._check_levels(pos, current_price, market_config)

            # Threshold-based change alerts
            if last_price is None:
                continue

            threshold = config.default_threshold
            if market_config and market_config.threshold is not None:
                threshold = market_config.threshold

            change = current_price - last_price
            if abs(change) >= threshold:
                arrow = "⬆️ UP" if change > 0 else "⬇️ DOWN"
                pct = change * 100
                msg = (
                    f"📊 <b>Price Alert</b> {arrow}\n\n"
                    f"<b>{pos.event_title}</b>\n"
                    f"{pos.title} — {pos.outcome}\n\n"
                    f"💰 {last_price:.2f} → {current_price:.2f} ({pct:+.1f}%)\n"
                    f"📦 {pos.size:.2f} shares"
                )
                await self._notifier.send_html(msg)

    async def _check_levels(self, pos, current_price: float, market_config) -> None:
        triggered = self._triggered.setdefault(pos.token_id, set())

        if market_config.above is not None:
            key = f"above:{market_config.above}"
            if current_price >= market_config.above and key not in triggered:
                triggered.add(key)
                msg = (
                    f"🎯 <b>Take Profit Alert</b>\n\n"
                    f"<b>{pos.event_title}</b>\n"
                    f"{pos.title} — {pos.outcome}\n\n"
                    f"💰 {current_price:.2f} crossed above {market_config.above:.2f}\n"
                    f"📦 {pos.size:.2f} shares"
                )
                await self._notifier.send_html(msg)
            elif current_price < market_config.above:
                triggered.discard(key)

        if market_config.below is not None:
            key = f"below:{market_config.below}"
            if current_price <= market_config.below and key not in triggered:
                triggered.add(key)
                msg = (
                    f"🛑 <b>Stop Loss Alert</b>\n\n"
                    f"<b>{pos.event_title}</b>\n"
                    f"{pos.title} — {pos.outcome}\n\n"
                    f"💰 {current_price:.2f} crossed below {market_config.below:.2f}\n"
                    f"📦 {pos.size:.2f} shares"
                )
                await self._notifier.send_html(msg)
            elif current_price > market_config.below:
                triggered.discard(key)
