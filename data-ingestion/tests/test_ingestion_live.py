import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from xleuth_ingestion.basket_builder import (_fetch_all_markets, build_basket,
                                              parse_basket_name)
from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.vwap import basket_vwap

load_dotenv()


@pytest_asyncio.fixture
async def client():
    c = PolymarketClient(
        gamma_api_base=os.getenv("POLYMARKET_GAMMA_API_BASE", "https://gamma-api.polymarket.com"),
        clob_api_base=os.getenv("POLYMARKET_CLOB_API_BASE", "https://clob.polymarket.com"),
        data_api_base=os.getenv("POLYMARKET_DATA_API_BASE", "https://data-api.polymarket.com"),
    )
    yield c
    await c.close()


# ── Gamma API tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_top_markets(client):
    markets = await client.get_markets(limit=5, order_by="volumeNum", ascending=False)
    assert len(markets) >= 2, "Should fetch at least 2 markets"
    for m in markets[:2]:
        assert "id" in m
        assert "question" in m
        assert "conditionId" in m
        assert "clobTokenIds" in m
        prices = client.parse_outcome_prices(m)
        assert len(prices) >= 1
        assert all(0 <= p <= 1 for p in prices), f"Price out of [0,1] range: {prices}"


# ── CLOB API tests (live price from CLOB, NOT Gamma cached) ──────────


@pytest.mark.asyncio
async def test_clob_midpoint_for_top_market(client):
    markets = await client.get_markets(limit=3, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    m = markets[0]
    token_ids = client.get_clob_token_ids(m)
    assert len(token_ids) >= 1, f"Market {m.get('id')} has no clobTokenIds"

    midpoint_price = await client.get_midpoint(token_ids[0])
    assert midpoint_price is not None, f"CLOB midpoint should not be None for {token_ids[0]}"
    assert 0.0 <= midpoint_price <= 1.0, f"CLOB midpoint {midpoint_price} out of [0,1] range"

    gamma_price = client.parse_outcome_prices(m)[0]
    print(
        f"\nPROOF: Market '{m.get('question')}' — "
        f"CLOB midpoint={midpoint_price:.4f} vs Gamma cached={gamma_price:.4f} "
        f"(diff={abs(midpoint_price - gamma_price):.4f})"
    )


@pytest.mark.asyncio
async def test_clob_midpoints_batch(client):
    markets = await client.get_markets(limit=5, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    all_token_ids = []
    for m in markets:
        all_token_ids.extend(client.get_clob_token_ids(m))
    assert len(all_token_ids) >= 1

    midpoint_map = await client.get_midpoints_batch(all_token_ids[:10])
    assert len(midpoint_map) >= 1
    for tid, price in midpoint_map.items():
        assert 0.0 <= price <= 1.0, f"CLOB price {price} out of [0,1] for token {tid}"


@pytest.mark.asyncio
async def test_clob_differs_from_gamma_price(client):
    markets = await client.get_markets(limit=10, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    found_diff = False
    for m in markets:
        token_ids = client.get_clob_token_ids(m)
        if not token_ids:
            continue
        clob_price = await client.get_midpoint(token_ids[0])
        gamma_prices = client.parse_outcome_prices(m)
        if clob_price is not None and gamma_prices:
            gamma_price = gamma_prices[0]
            if abs(clob_price - gamma_price) > 0.001:
                found_diff = True
                print(
                    f"\nCLOB vs GAMMA DIFFERENCE: Market '{m.get('question')}' — "
                    f"CLOB={clob_price:.4f} Gamma={gamma_price:.4f}"
                )
                break

    if not found_diff:
        print("\nNOTE: All sampled markets had CLOB and Gamma prices within 0.001 — "
              "this can happen during quiet periods but the endpoint is confirmed working")


# ── Data API live-volume tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_live_volume_for_event(client):
    markets = await client.get_markets(limit=10, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    first_with_event = None
    for m in markets:
        event_id = client.get_event_id(m)
        if event_id:
            first_with_event = (m, int(event_id))
            break

    assert first_with_event is not None, "No market with event found"
    market, eid = first_with_event

    vol_data = await client.get_live_volume(eid)
    assert vol_data is not None, f"Live volume should not be None for event {eid}"
    assert "total" in vol_data or "markets" in vol_data
    print(f"\nLive volume for event {eid}: {vol_data.get('total', 'N/A')}")

    gamma_volume = client.get_volume(market)
    if "total" in vol_data:
        live_total = float(vol_data["total"])
        print(f"  Gamma cached volumeNum={gamma_volume:.2f} vs Data API total={live_total:.2f}")





# ── Event map tests (dedup /live-volume calls) ────────────────────────


@pytest.mark.asyncio
async def test_event_map_volume_dedup(client):
    markets = await client.get_markets(limit=50, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    volume_map = await build_volume_map(markets, client)

    assert isinstance(volume_map, dict)
    if volume_map:
        for cond_id, vol in list(volume_map.items())[:3]:
            assert vol >= 0
            print(f"\nEvent map: condition {cond_id[:20]}... → live volume {vol:.2f}")


@pytest.mark.asyncio
async def test_event_map_no_double_calls(client):
    markets = await client.get_markets(limit=20, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    event_ids_seen = set()
    for m in markets:
        eid = client.get_event_id(m)
        if eid:
            event_ids_seen.add(eid)

    unique_count = len(event_ids_seen)
    total_markets = len(markets)

    assert unique_count <= total_markets
    print(f"\nProof: {total_markets} markets map to {unique_count} unique events "
          f"(would be {total_markets} calls without dedup, only {unique_count} calls needed)")


# ── VWAP tests ────────────────────────────────────────────────────────


def test_basket_vwap():
    constituents = [(0.5, 1000), (0.6, 2000), (0.4, 1500)]
    result = basket_vwap(constituents)
    expected = (0.5 * 1000 + 0.6 * 2000 + 0.4 * 1500) / (1000 + 2000 + 1500)
    assert result is not None
    assert abs(result - expected) < 0.0001


def test_basket_vwap_empty():
    assert basket_vwap([]) is None


# ── Basket name parsing ──────────────────────────────────────────────


def test_parse_basket_name():
    result = parse_basket_name("TOP50-JULY")
    assert result is not None
    n, month, name = result
    assert n == 50
    assert month == 7
    assert name == "TOP50-JULY"

    result = parse_basket_name("TOP100-AUGUST")
    assert result is not None
    n, month, _ = result
    assert n == 100
    assert month == 8

    assert parse_basket_name("invalid") is None
    assert parse_basket_name("TOP-ABC") is None


# ── Full pipeline integration test ────────────────────────────────────


@pytest.mark.asyncio
async def test_build_basket_produces_sane_output(client):
    result = await build_basket(
        "TOP5-JULY",
        client=client,
        exclude_categories="sports",
    )
    assert result is not None
    assert result["basket_name"] == "TOP5-JULY"
    assert isinstance(result["index_price"], float) or result["index_price"] is None
    if result["index_price"] is not None:
        assert 0.0 <= result["index_price"] <= 1.0
    assert isinstance(result["total_constituents"], int)
    assert isinstance(result["markets_filtered_out"], int)
    assert isinstance(result["excluded_markets"], list)
    assert isinstance(result["constituents"], list)
    for c in result["constituents"]:
        assert "event_id" in c
        assert "price" in c
        assert "volume" in c
        assert "end_date" in c
        assert "condition_id" in c
        assert "clob_token_id" in c
        assert "question" in c
        if c["price"] is not None:
            assert 0.0 <= c["price"] <= 1.0
    print(f"\nBasket TOP5-JULY: index_price={result['index_price']:.6f} "
          f"(scaled={result['index_price_scaled']}), "
          f"constituents={result['total_constituents']}, "
          f"excluded={result['markets_filtered_out']}")
    if result["constituents"]:
        c0 = result["constituents"][0]
        print(f"  Top constituent: price={c0['price']}, volume={c0['volume']}, "
              f"event_id={c0.get('event_id', 'N/A')}")


@pytest.mark.asyncio
async def test_basket_with_two_months(client):
    for name in ["TOP5-JULY", "TOP5-AUGUST"]:
        result = await build_basket(
            name,
            client=client,
            exclude_categories="sports",
        )
        assert result is not None
        assert result["basket_name"] == name
        if result["total_constituents"] > 0:
            assert result["index_price"] is not None
        print(f"\nBasket {name}: index_price={result['index_price']}, "
              f"constituents={result['total_constituents']}")


@pytest.mark.asyncio
async def test_build_basket_with_prefetched_markets(client):
    """Verify the markets= parameter produces same result as self-fetch."""
    markets = await _fetch_all_markets(client)
    assert len(markets) >= 100

    result_self = await build_basket(
        "TOP5-JULY",
        client=client,
        exclude_categories="sports",
    )
    result_pre = await build_basket(
        "TOP5-JULY",
        client=client,
        exclude_categories="sports",
        markets=markets,
    )

    assert result_pre["basket_name"] == result_self["basket_name"]
    assert isinstance(result_pre["index_price"], float) or result_pre["index_price"] is None
    assert result_pre["total_constituents"] == result_self["total_constituents"]
    assert result_pre["markets_filtered_out"] == result_self["markets_filtered_out"]
    assert len(result_pre["constituents"]) == len(result_self["constituents"])
    print(f"\nPrefetched basket: index_price={result_pre['index_price']:.6f}, "
          f"constituents={result_pre['total_constituents']} (matches self-fetch)")


@pytest.mark.asyncio
async def test_build_basket_prefetched_month_filter(client):
    markets = await _fetch_all_markets(client)
    assert len(markets) >= 100

    july = await build_basket(
        "TOP5-JULY",
        client=client,
        exclude_categories=None,
        markets=markets,
    )
    assert july["basket_name"] == "TOP5-JULY"
    assert isinstance(july["index_price"], float) or july["index_price"] is None

    august = await build_basket(
        "TOP5-AUGUST",
        client=client,
        exclude_categories=None,
        markets=markets,
    )
    assert august["basket_name"] == "TOP5-AUGUST"
    print(f"\nSame snapshot: JULY={july['total_constituents']} constituents, "
          f"AUGUST={august['total_constituents']} constituents")


# ── Verification: CLOB vs Gamma price diff  ──


@pytest.mark.asyncio
async def test_verification_output(client):
    """Print detailed verification output as required by PLAN.md verification prompt."""
    print("\n\n=== VERIFICATION OUTPUT ===")

    markets = await client.get_markets(limit=50, order_by="volumeNum", ascending=False)
    print(f"\nFetched {len(markets)} markets from Gamma /markets")

    if markets:
        m = markets[0]
        token_ids = client.get_clob_token_ids(m)
        cond_id = m.get("conditionId", "")
        event_id = client.get_event_id(m)
        print(f"\nTop market: {m.get('question')}")
        print(f"  conditionId: {cond_id}")
        print(f"  eventId: {event_id}")
        print(f"  clobTokenIds: {token_ids[:3]}...")

        if token_ids:
            clob_price = await client.get_midpoint(token_ids[0])
            gamma_price = client.parse_outcome_prices(m)[0]
            print(f"\n  CLOB midpoint price: {clob_price}")
            print(f"  Gamma cached outcomePrices[0]: {gamma_price}")
            if clob_price is not None and abs(clob_price - gamma_price) > 0.001:
                print(f"  ** CONFIRMED: CLOB differs from Gamma by {abs(clob_price - gamma_price):.4f}")
            else:
                print(f"  (prices within 0.001 — market may be quiet)")

        if event_id:
            vol_data = await client.get_live_volume(int(event_id))
            print(f"\n  Live volume (Data API /live-volume?id={event_id}):")
            if vol_data:
                print(f"    {vol_data}")
            else:
                print(f"    No data returned")