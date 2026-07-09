from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..notifier import Notifier
from ..polymarket.client import PolymarketClient, RateLimitError

if TYPE_CHECKING:
    from ..config_manager import ConfigManager

logger = logging.getLogger(__name__)


class PositionChanges:
    """Periodically report position value changes since last check."""

    def __init__(
        self,
        client: PolymarketClient,
        notifier: Notifier,
        config_mgr: ConfigManager,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._config_mgr = config_mgr
        # token_id -> (title, outcome, last_value, size, last_price)
        self._last_snapshot: dict[str, tuple[str, str, float, float, float]] = {}

    def export_state(self) -> dict[str, tuple[str, str, float, float, float]]:
        return dict(self._last_snapshot)

    def import_state(self, last_snapshot: dict[str, tuple[str, str, float, float, float]]) -> None:
        self._last_snapshot = last_snapshot

    async def tick(self) -> None:
        for wallet in self._config_mgr.config.my_wallets:
            try:
                await self._check_wallet(wallet)
            except RateLimitError as exc:
                logger.error("%s", exc)
                await self._notifier.send_html(f"⚠️ <b>Rate Limited</b>\nPolymarket API 限流，持仓变化监控暂停本轮。")
            except Exception:
                logger.exception("Position changes error for wallet %s", wallet)

    async def _check_wallet(self, wallet: str) -> None:
        positions = await self._client.get_positions(wallet)
        logger.info("Position changes: checking %d positions", len(positions))

        config = self._config_mgr.config.position_changes
        current_ids: set[str] = set()
        # (condition_id, change, abs_change, line) tuples
        entries: list[tuple[str, float, float, str]] = []
        total_change = 0.0

        for pos in positions:
            if not pos.token_id:
                continue
            current_ids.add(pos.token_id)
            value = pos.current_value
            cur_price = pos.cur_price or 0.0
            if config.min_value is not None and value < config.min_value:
                self._last_snapshot[pos.token_id] = (pos.title, pos.outcome, value, pos.size, cur_price)
                continue
            size = pos.size
            prev = self._last_snapshot.get(pos.token_id)

            if prev is not None:
                _, _, prev_value, prev_size, prev_price = prev
                if prev_size > 0 and size != prev_size:
                    logger.debug(
                        "Skipping %s [%s]: quantity changed %.4f → %.4f (buy/sell)",
                        pos.title, pos.outcome, prev_size, size,
                    )
                    self._last_snapshot[pos.token_id] = (pos.title, pos.outcome, value, size, cur_price)
                    continue
                change = value - prev_value
                threshold = config.default_threshold
                market_config = config.per_market.get(pos.condition_id)
                if market_config and market_config.threshold is not None:
                    threshold = market_config.threshold
                if abs(change) > threshold:
                    # Check overall P&L % filter (relative to cost basis)
                    initial = pos.initial_value
                    overall_pct = ((value - initial) / initial * 100) if initial else 0.0
                    matches_up = config.pct_up is not None and overall_pct >= config.pct_up
                    matches_down = config.pct_down is not None and overall_pct <= config.pct_down
                    either_set = config.pct_up is not None or config.pct_down is not None
                    if not either_set or matches_up or matches_down:
                        pct_str = f" / {overall_pct:+.1f}%" if initial else ""
                        url = f"https://polymarket.com/event/{pos.event_slug}"
                        title_link = f'<a href="{url}">{pos.title}</a>'
                        price_str = f"{cur_price * 100:.1f}" if cur_price else "?"
                        prev_price_str = f"{prev_price * 100:.1f}" if prev_price else "?"
                        entries.append((
                            pos.condition_id,
                            change,
                            abs(change),
                            f"• {title_link} [{pos.outcome} {pos.size:.2f}]\n"
                            f"  {prev_price_str}¢ → {price_str}¢\n"
                            f"  ${prev_value:.2f} → ${value:.2f} ({change:+.2f}{pct_str})",
                        ))

            self._last_snapshot[pos.token_id] = (pos.title, pos.outcome, value, size, cur_price)

        # Remove closed positions from snapshot without notifying
        for token_id in list(self._last_snapshot):
            if token_id not in current_ids:
                del self._last_snapshot[token_id]

        if not entries:
            return

        # Filter out split positions: same market (condition_id) with net change ≈ $0
        from collections import defaultdict
        net_by_condition: dict[str, float] = defaultdict(float)
        for cid, change, _, _ in entries:
            net_by_condition[cid] += change
        entries = [
            e for e in entries
            if abs(net_by_condition[e[0]]) > 0.01
        ]

        if not entries:
            return

        for _, change, _, _ in entries:
            total_change += change

        # Sort by absolute change descending
        entries.sort(key=lambda e: e[2], reverse=True)
        lines = [line for _, _, _, line in entries]

        header = f"📋 <b>Position Changes</b>\n<code>{wallet[:10]}...</code>\n"
        body = "\n\n".join(lines)
        footer = f"\n<b>Net change:</b> ${total_change:+.2f}"
        await self._notifier.send_html(f"{header}\n{body}\n{footer}", disable_preview=True)
