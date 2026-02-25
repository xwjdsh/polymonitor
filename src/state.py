from __future__ import annotations

import csv
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TIME_FMT = "%Y%m%d_%H%M%S"


class StateManager:
    def __init__(self, state_dir: str, max_age_seconds: int) -> None:
        self._dir = Path(state_dir)
        self._max_age = max_age_seconds

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _find_latest(self, prefix: str) -> Path | None:
        if not self._dir.exists():
            return None
        candidates = sorted(self._dir.glob(f"{prefix}_*.csv"), reverse=True)
        if not candidates:
            return None
        return candidates[0]

    def _is_fresh(self, path: Path) -> bool:
        stem = path.stem  # e.g. price_monitor_20260225_120000
        # Extract timestamp from the last two underscore-separated parts
        parts = stem.rsplit("_", 2)
        if len(parts) < 3:
            return False
        ts_str = f"{parts[-2]}_{parts[-1]}"
        try:
            ts = datetime.strptime(ts_str, _TIME_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= self._max_age

    def _remove_old(self, prefix: str) -> None:
        if not self._dir.exists():
            return
        for f in self._dir.glob(f"{prefix}_*.csv"):
            f.unlink()

    def _atomic_write(self, prefix: str, header: list[str], rows: list[list[str]]) -> None:
        self._ensure_dir()
        self._remove_old(prefix)
        ts = datetime.now(timezone.utc).strftime(_TIME_FMT)
        target = self._dir / f"{prefix}_{ts}.csv"
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".csv.tmp")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info("Saved state to %s", target)

    # ── Price Monitor ──────────────────────────────────────────

    def save_price_monitor(
        self,
        last_prices: dict[str, float],
        triggered: dict[str, set[str]],
    ) -> None:
        rows: list[list[str]] = []
        all_token_ids = set(last_prices) | set(triggered)
        for token_id in sorted(all_token_ids):
            price = last_prices.get(token_id, "")
            triggers = ",".join(sorted(triggered.get(token_id, set())))
            rows.append([token_id, str(price), triggers])
        self._atomic_write("price_monitor", ["token_id", "last_price", "triggered"], rows)

    def load_price_monitor(self) -> tuple[dict[str, float], dict[str, set[str]]] | None:
        path = self._find_latest("price_monitor")
        if path is None or not self._is_fresh(path):
            return None
        last_prices: dict[str, float] = {}
        triggered: dict[str, set[str]] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                token_id = row["token_id"]
                if row["last_price"]:
                    last_prices[token_id] = float(row["last_price"])
                if row["triggered"]:
                    triggered[token_id] = set(row["triggered"].split(","))
        logger.info("Loaded price monitor state from %s", path)
        return last_prices, triggered

    # ── Position Changes ───────────────────────────────────────

    def save_position_changes(
        self,
        last_snapshot: dict[str, tuple[str, str, float]],
    ) -> None:
        rows: list[list[str]] = []
        for token_id in sorted(last_snapshot):
            title, outcome, value = last_snapshot[token_id]
            rows.append([token_id, title, outcome, str(value)])
        self._atomic_write(
            "position_changes",
            ["token_id", "title", "outcome", "value"],
            rows,
        )

    def load_position_changes(self) -> dict[str, tuple[str, str, float]] | None:
        path = self._find_latest("position_changes")
        if path is None or not self._is_fresh(path):
            return None
        snapshot: dict[str, tuple[str, str, float]] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                snapshot[row["token_id"]] = (
                    row["title"],
                    row["outcome"],
                    float(row["value"]),
                )
        logger.info("Loaded position changes state from %s", path)
        return snapshot

    # ── Account Tracker ────────────────────────────────────────

    def save_account_tracker(self, last_seen: dict[str, str]) -> None:
        rows = [[addr, ts] for addr, ts in sorted(last_seen.items())]
        self._atomic_write("account_tracker", ["address", "last_seen"], rows)

    def load_account_tracker(self) -> dict[str, str] | None:
        path = self._find_latest("account_tracker")
        if path is None or not self._is_fresh(path):
            return None
        last_seen: dict[str, str] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                last_seen[row["address"]] = row["last_seen"]
        logger.info("Loaded account tracker state from %s", path)
        return last_seen
