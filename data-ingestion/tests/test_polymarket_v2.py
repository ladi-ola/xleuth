import json

import httpx
import pytest

from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.polymarket_client import PolymarketClient

CONDITION = "0x" + "ab" * 32


def client_for(payload, *, base="https://data-api.polymarket.com", status=200):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, content=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    client = PolymarketClient(data_api_base=base, http_client=http)
    return client, requests


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["https://data-api.polymarket.com", "https://data-api.polymarket.com/v2/"])
async def test_v2_path_query_envelope_and_share_units(base):
    client, requests = client_for({"data": {
        "taker_volume_total": 123.456789,
        "conditions": [{"condition_id": CONDITION, "taker_volume": 123.456789}],
    }}, base=base)
    try:
        result = await client.get_live_volume(73130)
    finally:
        await client.close()
    assert requests[0].url.path == "/v2/live-volume"
    assert requests[0].url.params["event_id"] == "73130"
    assert "id" not in requests[0].url.params
    assert result["markets"] == [{"market": CONDITION, "value": 123.456789}]
    assert result["volume_unit"] == "shares"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, -1, True, "100", float("nan"), float("inf")])
async def test_unavailable_invalid_volume_is_never_normalized_to_zero(value):
    client, _ = client_for({"data": {"conditions": [{"condition_id": CONDITION, "taker_volume": value}]}})
    try:
        with pytest.raises(ValueError):
            await client.get_live_volume(73130)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_duplicate_condition_rows_cannot_double_weight_the_basket():
    client, _ = client_for({"data": {"conditions": [
        {"condition_id": CONDITION, "taker_volume": 100},
        {"condition_id": CONDITION.upper(), "taker_volume": 100},
    ]}})
    try:
        with pytest.raises(ValueError, match="duplicate"):
            await client.get_live_volume(73130)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_event_dedup_is_preserved_with_v2():
    second = "0x" + "cd" * 32
    client, requests = client_for({"data": {"conditions": [
        {"condition_id": CONDITION, "taker_volume": 100},
        {"condition_id": second, "taker_volume": 200},
    ]}})
    markets = [
        {"conditionId": CONDITION, "events": [{"id": "73130"}]},
        {"conditionId": second, "events": [{"id": "73130"}]},
    ]
    try:
        result = await build_volume_map(markets, client)
    finally:
        await client.close()
    assert len(requests) == 1
    assert result == {CONDITION: 100, second: 200}


@pytest.mark.asyncio
async def test_http_failure_is_not_a_successful_empty_event():
    client, _ = client_for({"error": "unavailable"}, status=503)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_live_volume(73130)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_documented_empty_event_is_preserved():
    client, _ = client_for({"data": {"taker_volume_total": 0, "conditions": []}})
    try:
        result = await client.get_live_volume(73130)
    finally:
        await client.close()
    assert result["markets"] == []
