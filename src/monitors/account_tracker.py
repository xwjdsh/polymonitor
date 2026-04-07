from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from ..notifier import Notifier
from ..polymarket.client import PolymarketClient

if TYPE_CHECKING:
    from ..config_manager import ConfigManager

logger = logging.getLogger(__name__)


class AccountTracker:
    """Track top 10 positions of specific accounts and alert when a new position enters the top 10."""

    def __init__(
        self,
        client: PolymarketClient,
        notifier: Notifier,
        config_mgr: ConfigManager,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._config_mgr = config_mgr
        # address -> set of token_ids in last known top 10
        self._top10: dict[str, set[str]] = {}

    def export_state(self) -> dict[str, set[str]]:
        return {addr: set(tokens) for addr, tokens in self._top10.items()}

    def import_state(self, top10: dict[str, set[str]]) -> None:
        self._top10 = top10

    async def tick(self) -> None:
        """Run one tracking cycle."""
        for account in self._config_mgr.config.account_tracker.accounts:
            try:
                await self._check_account(account)
            except Exception:
                logger.exception("Account tracker error for %s", account.label)

    async def handle_overlap(self, _message: Any) -> None:
        """Handle /overlap command: show positions shared across tracked accounts."""
        accounts = self._config_mgr.config.account_tracker.accounts
        if not accounts:
            await self._notifier.send_html("No tracked accounts configured.")
            return

        # Fetch top 10 positions for each account
        # condition_id -> outcome -> list of (account_label, position)
        by_market: dict[str, dict[str, list[tuple[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        event_slugs: dict[str, str] = {}
        event_titles: dict[str, str] = {}

        for account in accounts:
            try:
                positions = await self._client.get_positions(account.address)
            except Exception:
                logger.exception("Failed to fetch positions for %s", account.label)
                continue
            top10 = sorted(positions, key=lambda p: p.current_value, reverse=True)[:10]
            for pos in top10:
                by_market[pos.condition_id][pos.outcome].append((account.label, pos))
                event_slugs[pos.condition_id] = pos.event_slug
                event_titles[pos.condition_id] = pos.title

        # Find markets where more than one account has any position
        shared = {
            cid: outcomes
            for cid, outcomes in by_market.items()
            if sum(len(holders) for holders in outcomes.values()) > 1
        }

        if not shared:
            await self._notifier.send_html("🔍 No overlapping top 10 positions found.")
            return

        def _sort_key(item: tuple[str, dict]) -> tuple[int, int]:
            outcomes = item[1]
            is_conflict = len(outcomes) > 1
            total = sum(len(holders) for holders in outcomes.values())
            return (int(is_conflict), -total)

        lines = ["🔍 <b>Top 10 Position Overlap</b>\n"]
        for cid, outcomes in sorted(shared.items(), key=_sort_key):
            slug = event_slugs.get(cid, "")
            title = event_titles.get(cid, cid)
            market_url = f"https://polymarket.com/event/{slug}"
            has_opposing = len(outcomes) > 1
            lines.append(f"📌 <a href=\"{market_url}\">{title}</a>{'  ⚔️' if has_opposing else ''}")
            for outcome, holders in sorted(outcomes.items()):
                holder_strs = ", ".join(
                    f"{label} ({pos.size:.0f}sh @ {pos.initial_value / pos.size * 100:.1f}¢ / ${pos.current_value:.0f})"
                    for label, pos in holders
                )
                lines.append(f"  <b>{outcome}</b>: {holder_strs}")
            lines.append("")

        await self._notifier.send_html("\n".join(lines).strip(), disable_preview=True)

    async def _check_account(self, account) -> None:
        positions = await self._client.get_positions(account.address)
        top10 = sorted(positions, key=lambda p: p.current_value, reverse=True)[:10]
        top10_ids = {p.token_id for p in top10}

        if account.address not in self._top10:
            # First run — initialize silently
            self._top10[account.address] = top10_ids
            logger.info("Account tracker: initialized top10 for %s", account.label)
            return

        prev_top10_ids = self._top10[account.address]
        new_entries = [p for p in top10 if p.token_id not in prev_top10_ids]

        self._top10[account.address] = top10_ids

        if not new_entries:
            logger.info("Account tracker: no new top10 positions for %s", account.label)
            return

        for pos in new_entries:
            profile_url = f"https://polymarket.com/profile/{account.address}"
            market_url = f"https://polymarket.com/event/{pos.event_slug}"
            msg = (
                f"🏆 <b>New Top 10 Position</b>\n\n"
                f"<a href=\"{profile_url}\"><b>{account.label}</b></a> (<code>{account.address[:10]}...</code>)\n\n"
                f"📈 <a href=\"{market_url}\">{pos.title}</a> — {pos.outcome}\n"
                f"💰 {pos.size:.2f} shares @ {pos.cur_price * 100:.1f}¢ (${pos.current_value:.2f})"
            )
            await self._notifier.send_html(msg, disable_preview=True)
