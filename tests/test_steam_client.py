from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

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
