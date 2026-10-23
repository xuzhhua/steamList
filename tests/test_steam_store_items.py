from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from app.services.steam_client import SteamClient

FIXTURES = Path(__file__).parent / "fixtures"
STORE_ITEMS_PATH = "/IStoreBrowseService/GetItems/v1/"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_client(handler) -> SteamClient:
    return SteamClient(cc="cn", min_interval=0, transport=httpx.MockTransport(handler))


def _handler(seen: list[httpx.Request], us_codes: set[int]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        payload = json.loads(request.url.params["input_json"])
        codes = {row["appid"] for row in payload["ids"]}
        if payload["context"]["country_code"] == "US":
            assert codes == us_codes, codes
            return httpx.Response(200, json=_load("store_items_us.json"))
        assert codes == {1245620, 730, 999999}, codes
        return httpx.Response(200, json=_load("store_items_cn.json"))

    return handler


def test_fetch_metas_uses_store_items_and_us_fallback():
    seen: list[httpx.Request] = []

    async def run():
        client = make_client(_handler(seen, {999999}))
        try:
            return await client.fetch_metas([1245620, 730, 999999])
        finally:
            await client.aclose()

    metas = asyncio.run(run())
    assert set(metas) == {1245620, 730, 999999}

    elden = metas[1245620]
    assert elden.name == "艾尔登法环"
    assert elden.header_image == (
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1245620/header.jpg?t=1790290043"
    )
    assert elden.short_description.startswith("艾尔登法环")
    assert elden.developers == "FromSoftware, Inc."
    assert elden.publishers == "FromSoftware, Inc., Bandai Namco Entertainment"
    assert elden.genres == ""
    assert elden.release_date == "2022-02-25"
    assert elden.is_free is None

    assert metas[730].is_free is True
    assert metas[999999].header_image == (
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/999999/"
        "c44857fe223dcf31ce603b756f8f01d89a4f0fce/header.jpg?t=7"
    )

    assert len(seen) == 2
    assert seen[0].url.host == "api.steampowered.com"
    assert seen[0].url.path == STORE_ITEMS_PATH
    assert "appids" not in seen[0].url.params
    assert json.loads(seen[0].url.params["input_json"])["context"]["language"] == "schinese"


def test_fetch_store_items_batches_then_retries_missing_in_us():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        payload = json.loads(request.url.params["input_json"])
        codes = [row["appid"] for row in payload["ids"]]
        if payload["context"]["country_code"] == "US":
            assert codes == [999999], codes
            return httpx.Response(200, json=_load("store_items_us.json"))
        assert len(codes) <= 2, codes
        return httpx.Response(200, json=_load("store_items_cn.json"))

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_metas([1245620, 730, 999999], batch_size=2)
        finally:
            await client.aclose()

    metas = asyncio.run(run())
    assert set(metas) == {1245620, 730, 999999}

    countries = [
        json.loads(request.url.params["input_json"])["context"]["country_code"]
        for request in seen
    ]
    assert countries == ["CN", "CN", "US"]
    assert len(seen) == 3


def test_fetch_store_items_tolerates_failed_batch():
    def handler(request: httpx.Request) -> httpx.Response:
        if "US" in request.url.params.get("input_json", ""):
            return httpx.Response(200, json={"response": {"store_items": []}})
        return httpx.Response(500)

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_metas([1245620])
        finally:
            await client.aclose()

    assert asyncio.run(run()) == {}


def test_fetch_store_items_backfills_missing_description():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/appdetails":
            assert request.url.params["appids"] == "1900"
            assert request.url.params["filters"] == "basic"
            return httpx.Response(
                200,
                json={
                    "1900": {
                        "success": True,
                        "data": {
                            "name": "Earth 2160",
                            "header_image": "https://cdn.example/1900.jpg",
                            "short_description": "经典 RTS。",
                            "developers": ["Reality Pump Studios"],
                            "publishers": ["Topware Interactive"],
                            "genres": [{"description": "Strategy"}, {"description": "RTS"}],
                            "release_date": {"date": "2005"},
                            "is_free": False,
                        },
                    }
                },
            )
        item = {
            "appid": 1900,
            "success": 1,
            "visible": True,
            "name": "Earth 2160",
            "basic_info": {"developers": [{"name": "Reality Pump Studios"}]},
            "assets": {},
            "release": {},
        }
        return httpx.Response(200, json={"response": {"store_items": [item]}})

    async def run():
        client = make_client(handler)
        try:
            return await client.fetch_metas([1900])
        finally:
            await client.aclose()

    metas = asyncio.run(run())
    meta = metas[1900]
    assert meta.name == "Earth 2160"
    assert meta.short_description == "经典 RTS。"
    assert meta.genres == "Strategy, RTS"
    assert meta.release_date == "2005"
    assert meta.is_free is False
    assert len(seen) == 2


def test_store_items_does_not_retry_us_when_already_us():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_load("store_items_us.json"))

    async def run():
        client = SteamClient(
            cc="us", min_interval=0, transport=httpx.MockTransport(handler)
        )
        try:
            return await client.fetch_store_items([999999])
        finally:
            await client.aclose()

    metas = asyncio.run(run())
    assert set(metas) == {999999}
    assert len(seen) == 1
    assert json.loads(seen[0].url.params["input_json"])["context"]["country_code"] == "US"
