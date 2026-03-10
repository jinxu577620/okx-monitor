from __future__ import annotations

import requests
from typing import List, Dict, Any

from config import OKX_REST_BASE, KLINE_LIMIT


class OKXPublicClient:
    def __init__(self, base_url: str = OKX_REST_BASE, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params or {}, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise RuntimeError(f"OKX API error: {data}")
        return data

    def get_candles(self, inst_id: str, bar: str, limit: int = KLINE_LIMIT) -> List[Dict[str, Any]]:
        data = self._get(
            "/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": str(limit)},
        )
        rows = data.get("data", [])
        candles = []
        for row in rows:
            candles.append(
                {
                    "ts": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        candles.reverse()
        return candles

    def get_ticker(self, inst_id: str) -> Dict[str, Any]:
        data = self._get("/api/v5/market/ticker", params={"instId": inst_id})
        row = data.get("data", [{}])[0]
        return {
            "instId": row.get("instId"),
            "last": float(row.get("last", 0) or 0),
            "bidPx": float(row.get("bidPx", 0) or 0),
            "askPx": float(row.get("askPx", 0) or 0),
            "high24h": float(row.get("high24h", 0) or 0),
            "low24h": float(row.get("low24h", 0) or 0),
            "vol24h": float(row.get("vol24h", 0) or 0),
        }
