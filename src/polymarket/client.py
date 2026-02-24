from __future__ import annotations

import logging
from typing import Any

import httpx

from .models import Activity, Market, Position

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


class PolymarketClient:
    """Async client for Polymarket public APIs."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Positions ──────────────────────────────────────────────

    async def get_positions(
        self,
        wallet: str,
        limit: int = 500,
        size_threshold: float = 0.1,
    ) -> list[Position]:
        data = await self._get(
            f"{DATA_API}/positions",
            params={
                "user": wallet,
                "limit": limit,
                "sizeThreshold": size_threshold,
            },
        )
        return [Position(**item) for item in data]

    # ── Prices ─────────────────────────────────────────────────

    async def get_midpoint(self, token_id: str) -> float:
        data = await self._get(f"{CLOB_API}/midpoint", params={"token_id": token_id})
        return float(data.get("mid", 0.0))

    async def get_price(self, token_id: str, side: str = "buy") -> float:
        data = await self._get(
            f"{CLOB_API}/price",
            params={"token_id": token_id, "side": side},
        )
        return float(data.get("price", 0.0))

    # ── Markets ────────────────────────────────────────────────

    async def get_market(self, condition_id: str) -> Market | None:
        data = await self._get(
            f"{GAMMA_API}/markets",
            params={"condition_id": condition_id},
        )
        if isinstance(data, list) and data:
            return Market(**data[0])
        return None

    # ── Activity ───────────────────────────────────────────────

    async def get_activity(
        self,
        wallet: str,
        limit: int = 100,
        start_time: str | None = None,
    ) -> list[Activity]:
        params: dict[str, Any] = {"user": wallet, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        data = await self._get(f"{DATA_API}/activity", params=params)
        return [Activity(**item) for item in data]
