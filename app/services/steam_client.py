"""Async Steam store client with polite rate limiting.

Only public, undocumented-in-places storefront endpoints are used:

* ``store.steampowered.com/api/appdetails``  - price_overview + metadata
* ``store.steampowered.com/api/storesearch`` - search suggestions
* ``api.steampowered.com/IWishlistService/GetWishlist/v1`` - public wishlist

Steam documents roughly 200 requests / 5 minutes for appdetails. We stay far
below that: one request per 100 appids, with extra spacing between batches.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

logger = logging.getLogger("steamlist.steam")

APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
WISHLIST_URL = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
PROFILE_XML_URL = "https://steamcommunity.com/profiles/{steamid}/?xml=1"
VANITY_XML_URL = "https://steamcommunity.com/id/{vanity}/?xml=1"
WISHLIST_DATA_URL = "https://store.steampowered.com/wishlist/profiles/{steamid}/wishlistdata/"
HEADER_IMAGE_URL = "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"

_STEAMID64_RE = re.compile(r"^\d{17}$")
_PROFILE_URL_RE = re.compile(r"/profiles/(\d{17})")
_VANITY_URL_RE = re.compile(r"/id/([^/?#]+)")
_VANITY_RE = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")


def xml_value(xml_text: str, tag: str) -> str:
    """Read a simple ``<tag>`` value (with or without CDATA) from Steam XML."""
    match = re.search(
        rf"<{tag}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{tag}>",
        xml_text or "",
        re.S,
    )
    return match.group(1).strip() if match else ""


BATCH_SIZE = 100
DEFAULT_CURRENCY = {
    "cn": "CNY",
    "us": "USD",
    "hk": "HKD",
    "tw": "TWD",
    "jp": "JPY",
    "gb": "GBP",
    "de": "EUR",
}


class SteamError(RuntimeError):
    """Raised when Steam cannot be reached after retries."""


@dataclass(frozen=True)
class PriceResult:
    appid: int
    currency: str
    initial_cents: int
    final_cents: int
    discount_percent: int
    available: bool
    is_free: bool


@dataclass(frozen=True)
class GameMeta:
    appid: int
    name: str
    header_image: str
    short_description: str
    developers: str
    publishers: str
    genres: str
    release_date: str
    is_free: bool


@dataclass(frozen=True)
class SearchItem:
    appid: int
    name: str
    header_image: str
    price_cents: int | None
    currency: str | None


def parse_price_payload(appid: int, entry: Mapping[str, Any] | None, cc: str) -> PriceResult | None:
    """Parse one ``appdetails`` entry into a :class:`PriceResult`.

    Returns ``None`` when the appid is unknown to the store (``success=false``).
    Free games are reported as available with a zero price; delisted games are
    reported as unavailable rather than 0 CNY.
    """
    if not entry or not entry.get("success"):
        return None
    data: Mapping[str, Any] = entry.get("data") or {}
    is_free = bool(data.get("is_free"))
    overview = data.get("price_overview") or {}
    currency = overview.get("currency") or DEFAULT_CURRENCY.get(cc, "")
    if not overview:
        if is_free:
            return PriceResult(appid, currency, 0, 0, 0, available=True, is_free=True)
        return PriceResult(appid, currency, 0, 0, 0, available=False, is_free=False)
    return PriceResult(
        appid=appid,
        currency=currency,
        initial_cents=int(overview.get("initial") or 0),
        final_cents=int(overview.get("final") or 0),
        discount_percent=int(overview.get("discount_percent") or 0),
        available=True,
        is_free=is_free,
    )


class SteamClient:
    def __init__(
        self,
        cc: str = "cn",
        lang: str = "schinese",
        proxy: str | None = None,
        timeout: float = 25.0,
        min_interval: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cc = cc
        self.lang = lang
        self.min_interval = min_interval
        kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(timeout),
            "headers": {
                "User-Agent": "SteamList/0.1 (self-hosted price tracker)",
                "Accept": "application/json",
            },
        }
        if transport is not None:
            kwargs["transport"] = transport
        elif proxy:
            kwargs["proxy"] = proxy
        self._client = httpx.AsyncClient(**kwargs)
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SteamClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    async def _request(self, url: str, params: Mapping[str, Any]) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            await self._throttle()
            try:
                response = await self._client.get(url, params=dict(params) if params else None)
            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(2 ** attempt)
                continue
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:  # pragma: no cover - Steam always returns JSON
                    last_error = SteamError(f"invalid JSON from {url}: {exc}")
                    break
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else float(2 ** attempt)
                logger.warning(
                    "Steam HTTP %s for %s; retrying in %.0fs (attempt %s/4)",
                    response.status_code,
                    url,
                    delay,
                    attempt + 1,
                )
                await asyncio.sleep(min(delay, 60.0))
                last_error = SteamError(f"HTTP {response.status_code} from {url}")
                continue
            raise SteamError(f"Steam request failed with HTTP {response.status_code}: {url}")
        raise SteamError(f"Steam request failed after retries: {last_error}")

    async def fetch_prices(self, appids: Sequence[int]) -> dict[int, PriceResult | None]:
        """Fetch current prices for up to ``len(appids)`` games (100 per request)."""
        unique = [int(a) for a in dict.fromkeys(appids) if int(a) > 0]
        results: dict[int, PriceResult | None] = {}
        for index in range(0, len(unique), BATCH_SIZE):
            chunk = unique[index : index + BATCH_SIZE]
            try:
                payload = await self._request(
                    APP_DETAILS_URL,
                    {
                        "appids": ",".join(str(a) for a in chunk),
                        "filters": "price_overview",
                        "cc": self.cc,
                        "l": self.lang,
                    },
                )
            except SteamError as exc:
                logger.warning("price batch failed (%s apps): %s", len(chunk), exc)
                for appid in chunk:
                    results[appid] = None
                continue
            for appid in chunk:
                entry = payload.get(str(appid)) if isinstance(payload, dict) else None
                results[appid] = parse_price_payload(appid, entry, self.cc)
            if index + BATCH_SIZE < len(unique):
                await asyncio.sleep(random.uniform(1.0, 3.0))
        return results

    def _parse_meta(self, appid: int, entry: Mapping[str, Any] | None) -> GameMeta | None:
        if not entry or not entry.get("success"):
            return None
        data = entry.get("data") or {}
        return GameMeta(
            appid=appid,
            name=str(data.get("name") or ""),
            header_image=str(data.get("header_image") or HEADER_IMAGE_URL.format(appid=appid)),
            short_description=str(data.get("short_description") or ""),
            developers=", ".join(data.get("developers") or []),
            publishers=", ".join(data.get("publishers") or []),
            genres=", ".join(g.get("description", "") for g in (data.get("genres") or []) if g),
            release_date=str((data.get("release_date") or {}).get("date") or ""),
            is_free=bool(data.get("is_free")),
        )

    async def fetch_app(self, appid: int) -> tuple[GameMeta | None, PriceResult | None]:
        """One ``appdetails`` call without filters: metadata + price together."""
        payload = await self._request(
            APP_DETAILS_URL, {"appids": str(appid), "cc": self.cc, "l": self.lang}
        )
        entry = payload.get(str(appid)) if isinstance(payload, dict) else None
        return self._parse_meta(appid, entry), parse_price_payload(appid, entry, self.cc)

    async def fetch_meta(self, appid: int) -> GameMeta | None:
        meta, _ = await self.fetch_app(appid)
        return meta

    async def fetch_metas(self, appids: Sequence[int], batch_size: int = 50) -> dict[int, GameMeta]:
        """Fetch metadata for many games with few requests (no price filter)."""
        unique = [int(a) for a in dict.fromkeys(appids) if int(a) > 0]
        metas: dict[int, GameMeta] = {}
        for index in range(0, len(unique), batch_size):
            chunk = unique[index : index + batch_size]
            try:
                payload = await self._request(
                    APP_DETAILS_URL,
                    {"appids": ",".join(str(a) for a in chunk), "cc": self.cc, "l": self.lang},
                )
            except SteamError as exc:
                logger.warning("metadata batch failed (%s apps): %s", len(chunk), exc)
                continue
            for appid in chunk:
                meta = self._parse_meta(appid, (payload or {}).get(str(appid)))
                if meta is not None:
                    metas[appid] = meta
            if index + batch_size < len(unique):
                await asyncio.sleep(random.uniform(1.0, 3.0))
        return metas

    async def search(self, term: str, limit: int = 12) -> list[SearchItem]:
        term = (term or "").strip()
        if len(term) < 2:
            return []
        payload = await self._request(
            STORE_SEARCH_URL, {"term": term, "cc": self.cc, "l": self.lang}
        )
        items: list[SearchItem] = []
        for row in (payload.get("items") or [])[:limit]:
            appid = int(row.get("id") or 0)
            if not appid:
                continue
            price = row.get("price") or {}
            items.append(
                SearchItem(
                    appid=appid,
                    name=str(row.get("name") or ""),
                    header_image=HEADER_IMAGE_URL.format(appid=appid),
                    price_cents=int(price["final"]) if price.get("final") is not None else None,
                    currency=price.get("currency"),
                )
            )
        return items

    async def fetch_wishlist(self, steamid: str) -> list[int]:
        steamid = (steamid or "").strip()
        if not steamid.isdigit():
            raise SteamError("SteamID must be a 17-digit numeric id")
        payload = await self._request(WISHLIST_URL, {"steamid": steamid})
        response = payload.get("response") or {}
        return [int(item["appid"]) for item in (response.get("items") or []) if item.get("appid")]

    async def _get_text(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        """GET a community/store HTML/XML page (these are not JSON endpoints)."""
        last_error: Exception | None = None
        for attempt in range(3):
            await self._throttle()
            try:
                response = await self._client.get(
                    url,
                    params=dict(params) if params else None,
                    follow_redirects=follow_redirects,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                await asyncio.sleep(2 ** attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                delay = float(2 ** attempt)
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = float(retry_after)
                logger.warning("Steam HTTP %s for %s; retrying in %.0fs", response.status_code, url, delay)
                await asyncio.sleep(min(delay, 30.0))
                last_error = SteamError(f"HTTP {response.status_code} from {url}")
                continue
            return response
        raise SteamError(f"Steam request failed after retries: {last_error}")

    async def resolve_steamid(self, value: str) -> str:
        """Accept a SteamID64, a profile URL or a custom vanity name.

        Steam's wishlist API only accepts the 17-digit SteamID64; vanity names are
        resolved through the public profile XML endpoint (no API key needed).
        """
        raw = (value or "").strip()
        if not raw:
            raise SteamError("SteamID 不能为空")
        match = _PROFILE_URL_RE.search(raw)
        if match:
            return match.group(1)
        if _STEAMID64_RE.match(raw):
            return raw
        if raw.isdigit():
            raise SteamError(
                "SteamID 必须是 17 位数字（以 7656 开头），或填写个人资料链接 / 自定义链接名"
            )
        vanity_match = _VANITY_URL_RE.search(raw)
        vanity = vanity_match.group(1) if vanity_match else raw
        if not _VANITY_RE.match(vanity):
            raise SteamError("无法识别的 SteamID / 个人资料链接，请填写 17 位数字、资料链接或自定义链接名")
        response = await self._get_text(VANITY_XML_URL.format(vanity=vanity))
        steamid = xml_value(response.text, "steamID64")
        if response.status_code != 200 or not _STEAMID64_RE.match(steamid):
            raise SteamError(f"未找到自定义链接名「{vanity}」对应的 Steam 个人资料，请检查链接名是否正确")
        return steamid

    async def fetch_profile(self, steamid: str) -> dict[str, str] | None:
        """Public profile summary: persona name and privacy state."""
        response = await self._get_text(PROFILE_XML_URL.format(steamid=steamid))
        if response.status_code != 200:
            return None
        text = response.text
        found = xml_value(text, "steamID64")
        if not found and not xml_value(text, "privacyState"):
            return None
        return {
            "steamid": found or steamid,
            "persona": xml_value(text, "steamID") or found or steamid,
            "privacy": xml_value(text, "privacyState"),
            "visibility": xml_value(text, "visibilityState"),
        }

    async def wishlist_visibility(self, steamid: str) -> str:
        """Whether the store can show this wishlist: ``visible`` / ``hidden`` / ``unknown``."""
        response = await self._get_text(
            WISHLIST_DATA_URL.format(steamid=steamid),
            params={"p": "0"},
            follow_redirects=False,
        )
        if response.status_code == 200:
            return "visible"
        if 300 <= response.status_code < 400 or response.status_code in (401, 403):
            return "hidden"
        return "unknown"

