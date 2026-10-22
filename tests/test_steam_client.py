from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.services.steam_auth import SteamAuthError
from app.services.steam_client import SteamClient, SteamError, parse_price_payload

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_client(handler, **kwargs) -> SteamClient:
    return SteamClient(cc="cn", min_interval=0, transport=httpx.MockTransport(handler), **kwargs)


def test_parse_price_payload_normal():
    result = parse_price_payload(1245620, load("appdetails_batch.json")["1245620"], "cn")
    assert result.available is True
    assert result.final_cents == 29800
    assert result.discount_percent == 0
    assert result.currency == "CNY"


def test_parse_price_payload_free_game():
    result = parse_price_payload(730, load("appdetails_batch.json")["730"], "cn")
    assert result.available is True
    assert result.is_free is True
    assert result.final_cents == 0


def test_parse_price_payload_delisted_is_unavailable():
    result = parse_price_payload(999999, load("appdetails_batch.json")["999999"], "cn")
    assert result.available is False
    assert result.final_cents == 0


def test_parse_price_payload_unknown_appid():
    assert parse_price_payload(1, {"success": False}, "cn") is None


def test_fetch_prices_batches_and_sends_filters():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load("appdetails_batch.json"))

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_prices([1245620, 1086940, 730, 999999])
        finally:
            await client.aclose()

    results = asyncio.run(run())
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/api/appdetails"
    assert request.url.params["filters"] == "price_overview"
    assert request.url.params["appids"] == "1245620,1086940,730,999999"
    assert results[1245620].final_cents == 29800
    assert results[1086940].discount_percent == 10
    assert results[730].is_free is True
    assert results[999999].available is False


def test_fetch_prices_survives_failed_batch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_prices([1, 2])
        finally:
            await client.aclose()

    results = asyncio.run(run())
    assert results == {1: None, 2: None}


def test_retries_on_429_then_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=load("appdetails_meta.json"))

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_meta(1245620)
        finally:
            await client.aclose()

    meta = asyncio.run(run())
    assert calls["n"] == 2
    assert meta.name == "ELDEN RING"


def test_fetch_meta_parses_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["appids"] == "1245620"
        assert "filters" not in request.url.params
        return httpx.Response(200, json=load("appdetails_meta.json"))

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_meta(1245620)
        finally:
            await client.aclose()

    meta = asyncio.run(run())
    assert meta.developers == "FromSoftware, Inc."
    assert meta.genres == "Action, RPG"
    assert meta.release_date == "24 Feb, 2022"
    assert meta.header_image.endswith("header.jpg")


def test_search_parses_items():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/storesearch/"
        assert request.url.params["term"] == "赛博朋克"
        return httpx.Response(200, json=load("storesearch.json"))

    async def run():
        client = make_client(handler)
        try:
            return await client.search("赛博朋克")
        finally:
            await client.aclose()

    items = asyncio.run(run())
    assert [i.name for i in items] == ["赛博朋克 2077", "赛博朋克 2077：往日之影"]
    assert items[0].price_cents == 14900
    assert items[1].price_cents is None
    assert items[0].header_image.endswith("header.jpg")


def test_search_short_term_returns_empty_without_request():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    async def run():
        client = make_client(handler)
        try:
            return await client.search("a")
        finally:
            await client.aclose()

    assert asyncio.run(run()) == []


def test_wishlist_parsing_and_empty_response():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["steamid"] == "76561197960287930":
            return httpx.Response(200, json=load("wishlist.json"))
        return httpx.Response(200, json={"response": {}})

    async def run():
        client = make_client(handler)
        try:
            return (
                await client.fetch_wishlist("76561197960287930"),
                await client.fetch_wishlist("76561190000000000"),
            )
        finally:
            await client.aclose()

    with_items, empty = asyncio.run(run())
    assert with_items == [1245620, 1086940]
    assert empty == []


def test_wishlist_requires_numeric_steamid():
    async def run():
        client = make_client(lambda request: httpx.Response(200, json={}))
        try:
            with pytest.raises(SteamError):
                await client.fetch_wishlist("vanity-name")
        finally:
            await client.aclose()

    asyncio.run(run())


PROFILE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<profile>
\t<steamID64>76561197968052866</steamID64>
\t<steamID><![CDATA[Gaben]]></steamID>
\t<privacyState>public</privacyState>
\t<visibilityState>3</visibilityState>
</profile>"""

PRIVATE_PROFILE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<profile>
\t<privacyState>private</privacyState>
\t<visibilityState>1</visibilityState>
\t<stateMessage><![CDATA[This profile is private.]]></stateMessage>
</profile>"""


def test_resolve_steamid_accepts_id_and_profile_url_without_requests():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError(f"unexpected request: {request.url}")

    async def run():
        client = make_client(handler)
        try:
            return [
                await client.resolve_steamid("76561197960287930"),
                await client.resolve_steamid("https://steamcommunity.com/profiles/76561197960287930/"),
                await client.resolve_steamid("  steamcommunity.com/profiles/76561197960287930?l=schinese  "),
            ]
        finally:
            await client.aclose()

    assert asyncio.run(run()) == ["76561197960287930"] * 3


def test_resolve_steamid_vanity_uses_profile_xml():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=PROFILE_XML)

    async def run():
        client = make_client(handler)
        try:
            return (
                await client.resolve_steamid("gaben"),
                await client.resolve_steamid("https://steamcommunity.com/id/gaben/"),
            )
        finally:
            await client.aclose()

    assert asyncio.run(run()) == ("76561197968052866", "76561197968052866")
    assert all("steamcommunity.com/id/gaben/" in url for url in seen)


def test_resolve_steamid_unknown_vanity_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=PRIVATE_PROFILE_XML)

    async def run():
        client = make_client(handler)
        try:
            with pytest.raises(SteamError):
                await client.resolve_steamid("no-such-profile")
        finally:
            await client.aclose()

    asyncio.run(run())


def test_resolve_steamid_rejects_short_numeric_id():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    async def run():
        client = make_client(handler)
        try:
            with pytest.raises(SteamError):
                await client.resolve_steamid("12345")
        finally:
            await client.aclose()

    asyncio.run(run())


def test_fetch_profile_parses_privacy_state():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/profiles/76561197968052866/" in str(request.url)
        return httpx.Response(200, text=PROFILE_XML)

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_profile("76561197968052866")
        finally:
            await client.aclose()

    profile = asyncio.run(run())
    assert profile is not None
    assert profile["persona"] == "Gaben"
    assert profile["privacy"] == "public"


def test_fetch_profile_missing_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_profile("76561190000000000")
        finally:
            await client.aclose()

    assert asyncio.run(run()) is None


def test_fetch_profile_private_profile_reports_privacy():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=PRIVATE_PROFILE_XML)

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_profile("76561197960287930")
        finally:
            await client.aclose()

    profile = asyncio.run(run())
    assert profile is not None
    assert profile["privacy"] == "private"
    assert profile["steamid"] == "76561197960287930"


def test_wishlist_visibility_detects_redirect_and_public():
    def handler(request: httpx.Request) -> httpx.Response:
        if "76561197960287930" in str(request.url):
            return httpx.Response(302, headers={"location": "https://steamcommunity.com/login"})
        return httpx.Response(200, json={"1": {"name": "ELDEN RING"}})

    async def run():
        client = make_client(handler)
        try:
            return (
                await client.wishlist_visibility("76561197960287930"),
                await client.wishlist_visibility("76561197968052866"),
            )
        finally:
            await client.aclose()

    assert asyncio.run(run()) == ("hidden", "visible")


def test_get_text_keeps_query_string_when_params_omitted():
    """httpx drops the existing query when ``params={}`` is passed; this guards the XML link."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=PROFILE_XML)

    async def run():
        client = make_client(handler)
        try:
            response = await client._get_text(
                "https://steamcommunity.com/profiles/76561197968052866/?xml=1"
            )
            return response.text
        finally:
            await client.aclose()

    assert asyncio.run(run()) == PROFILE_XML
    assert seen == ["https://steamcommunity.com/profiles/76561197968052866/?xml=1"]



STEAMID = "76561197960287930"


def test_fetch_wishlist_private_sends_cookie_and_pages():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = request.url.params.get("p")
        if page == "0":
            data = {str(1000 + i): {"name": f"game {i}"} for i in range(100)}
        else:
            data = {"2000": {"name": "last"}}
        return httpx.Response(200, json=data)

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_wishlist_private(STEAMID, "token-1")
        finally:
            await client.aclose()

    appids = asyncio.run(run())
    assert len(appids) == 101
    assert appids[0] == 1000
    assert appids[-1] == 2000
    assert [r.url.params.get("p") for r in seen] == ["0", "1"]
    assert seen[0].headers["cookie"] == "steamLoginSecure=" + STEAMID + "||token-1"


def test_fetch_wishlist_private_redirect_means_relogin():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://store.steampowered.com/login/"})

    async def run():
        client = make_client(handler)
        try:
            await client.fetch_wishlist_private(STEAMID, "expired")
        finally:
            await client.aclose()

    with pytest.raises(SteamAuthError, match="重新扫码"):
        asyncio.run(run())


def test_fetch_wishlist_private_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async def run():
        client = make_client(handler)
        try:
            await client.fetch_wishlist_private(STEAMID, "token")
        finally:
            await client.aclose()

    with pytest.raises(SteamError):
        asyncio.run(run())


def test_fetch_wishlist_private_empty_object():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_wishlist_private(STEAMID, "token")
        finally:
            await client.aclose()

    assert asyncio.run(run()) == []
