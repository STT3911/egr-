"""Client for MNS GRP public API.

Docs/overview: https://grp.nalog.gov.by/grp/rest-api
Example request (from docs / community posts):
  http://grp.nalog.gov.by/api/grp-public/data?unp=100582333&charset=UTF-8&type=json

We request JSON and normalize the payload into a simple dict.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


class GRPClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 20.0):
        self.base_url = (base_url or getattr(settings, "GRP_API_URL", None) or "http://grp.nalog.gov.by/api/grp-public/data").rstrip("/")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers
        )

    async def close(self):
        await self._client.aclose()

    async def get_taxpayer(self, unp: int) -> Dict[str, Any]:
        """Fetch taxpayer data by UNP.

        Returns:
          A dict with fields like VUNP, VNAIMP, ...
        Raises:
          httpx.HTTPError on transport problems
          ValueError if server returns unexpected/invalid JSON
        """
        params = {
            "unp": str(unp),
            "charset": "UTF-8",
            "type": "json",
        }

        try:
            resp = await self._client.get(self.base_url, params=params, headers={"Accept": "application/json"})

            # Handle different status codes
            if resp.status_code == 404:
                # UNP not found - return empty dict instead of raising
                return {}
            elif resp.status_code == 429:
                # Rate limit - raise specific error
                raise httpx.HTTPStatusError("429 Rate limit exceeded", request=resp.request, response=resp)
            elif resp.status_code >= 400:
                # Other client/server errors
                resp.raise_for_status()

            # Some servers may return JSON with text/plain content-type, so we parse manually.
            try:
                data = resp.json()
            except Exception as e:
                raise ValueError(f"GRP returned non-JSON response (status={resp.status_code}): {e}")

            # Normalize common shapes
            if isinstance(data, list):
                # Some APIs return an array with a single row
                if len(data) == 0:
                    return {}
                if isinstance(data[0], dict):
                    return data[0]
                return {"value": data[0]}

            if isinstance(data, dict):
                # Check if data is empty or contains error
                if not data:
                    return {}

                # Some wrappers like {"row": {...}}
                for key in ("row", "ROW", "data", "DATA"):
                    inner = data.get(key)
                    if isinstance(inner, dict):
                        return inner

                return data

            raise ValueError(f"Unexpected GRP payload type: {type(data)}")

        except httpx.HTTPError:
            raise
        except Exception:
            raise
