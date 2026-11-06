from typing import Any
import math

import httpx


class PolymarketClient:
    def __init__(
        self,
        gamma_api_base: str = "https://gamma-api.polymarket.com",
        clob_api_base: str = "https://clob.polymarket.com",
        data_api_base: str = "https://data-api.polymarket.com",
        http_client: httpx.AsyncClient | None = None,
    ):
        self.gamma_base = gamma_api_base.rstrip("/")
        self.clob_base = clob_api_base.rstrip("/")
        self.data_base = data_api_base.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ── Gamma API (market discovery) ──────────────────────────────────

    async def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "volumeNum",
        ascending: bool = False,
        closed: bool = False,
        active: bool = True,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "limit": limit,
            "offset": offset,
            "order": order_by,
            "ascending": str(ascending).lower(),
            "closed": str(closed).lower(),
        }
        if active:
            params["active"] = "true"
        resp = await self._client.get(f"{self.gamma_base}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_market(self, market_id: str | int) -> dict[str, Any]:
        resp = await self._client.get(f"{self.gamma_base}/markets/{market_id}")
        resp.raise_for_status()
        return resp.json()

    # ── CLOB API (live tick price) ──────────────────────────────────
    # Public, read-only — NO API key or wallet signing required.

    async def get_midpoint(self, token_id: str) -> float | None:
        resp = await self._client.get(
            f"{self.clob_base}/midpoint",
            params={"token_id": token_id},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        mid = data.get("mid")
        if mid is None:
            return None
        return float(mid)

    async def get_midpoints_batch(self, token_ids: list[str]) -> dict[str, float]:
        if not token_ids:
            return {}
        resp = await self._client.post(
            f"{self.clob_base}/midpoints",
            json=[{"token_id": tid} for tid in token_ids],
        )
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json()
        return {tid: float(price) for tid, price in data.items()}

    # ── Data API (live volume) ──────────────────────────────────────

    async def get_live_volume(self, event_id: int) -> dict[str, Any] | None:
        # Data API v1 now returns 410. The documented v2 replacement wraps
        # cumulative one-side volume (SHARES, not USDC) in data.conditions.
        # Keep the event_map adapter shape, never mix these weights with Gamma
        # volumeNum if a live value is absent.
        base = self.data_base if self.data_base.endswith("/v2") else f"{self.data_base}/v2"
        resp = await self._client.get(
            f"{base}/live-volume",
            params={"event_id": event_id},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        envelope = resp.json()
        if not isinstance(envelope, dict):
            raise ValueError("invalid Data API v2 live-volume envelope")
        payload = envelope.get("data")
        if payload is None:
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("conditions"), list):
            raise ValueError("invalid Data API v2 live-volume envelope")
        markets = []
        seen = set()
        for entry in payload["conditions"]:
            if not isinstance(entry, dict):
                raise ValueError("invalid Data API v2 live-volume row")
            condition = entry.get("condition_id")
            volume = entry.get("taker_volume")
            if not isinstance(condition, str) or not condition:
                raise ValueError("missing live-volume condition identifier")
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume < 0:
                raise ValueError("missing or invalid live taker volume")
            normalized = condition.lower().removeprefix("0x")
            if normalized in seen:
                raise ValueError("duplicate condition in Data API v2 live volume")
            seen.add(normalized)
            markets.append({"market": condition, "value": float(volume)})
        return {"markets": markets, "volume_unit": "shares", "volume_source": "data_api_v2_taker"}

    # ── Gamma field helpers (for reference/fallback only) ────────────

    @staticmethod
    def parse_outcomes(market: dict[str, Any]) -> list[str]:
        raw = market.get("outcomes", "[]")
        if isinstance(raw, str):
            import json
            return json.loads(raw)
        return raw

    @staticmethod
    def parse_outcome_prices(market: dict[str, Any]) -> list[float]:
        raw = market.get("outcomePrices", "[]")
        if isinstance(raw, str):
            import json
            return [float(p) for p in json.loads(raw)]
        return [float(p) for p in raw]

    @staticmethod
    def get_volume(market: dict[str, Any]) -> float:
        return float(market.get("volumeNum", 0) or 0)

    @staticmethod
    def get_category(market: dict[str, Any]) -> str | None:
        events = market.get("events", [])
        if events:
            return events[0].get("category")
        return market.get("category")

    @staticmethod
    def get_event_id(market: dict[str, Any]) -> str | None:
        events = market.get("events", [])
        if events:
            return str(events[0].get("id", ""))
        return None

    @staticmethod
    def get_clob_token_ids(market: dict[str, Any]) -> list[str]:
        raw = market.get("clobTokenIds", "[]")
        if isinstance(raw, str):
            import json
            return json.loads(raw)
        return raw if raw else []
