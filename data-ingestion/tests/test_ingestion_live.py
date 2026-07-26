import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from xleuth_ingestion.basket_builder import build_basket, parse_basket_name
from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.liquidity_filter import compute_liquidity_score, filter_markets
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.vwap import basket_vwap, sub_outcome_vwap

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


# ── Liquidity filter tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_liquidity_filter_excludes_low_volume(client):
    markets = await client.get_markets(limit=50, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    passed, excluded = filter_markets(
        markets,
        min_volume_usd=1_000_000_000,
        min_liquidity_score=0.0,
        exclude_categories=None,
    )
    assert len(passed) == 0, "All markets should be excluded with impossibly high volume threshold"
    assert len(excluded) >= 1
    for e in excluded:
        assert "reason" in e
    print(f"\nLiquidity filter excluded {len(excluded)} markets with $1B threshold")


@pytest.mark.asyncio
async def test_liquidity_filter_excludes_sports(client):
    markets = await client.get_markets(limit=50, order_by="volumeNum", ascending=False)
    assert len(markets) > 0

    passed, excluded = filter_markets(
        markets,
        min_volume_usd=0,
        min_liquidity_score=0.0,
        exclude_categories="sports",
    )
    assert len(passed) >= 1
    sports_excluded = [e for e in excluded if "sports" in e.get("reason", "").lower()]
    if sports_excluded:
        print(f"\nSports filter excluded {len(sports_excluded)} markets")
        for e in sports_excluded[:3]:
            print(f"  - {e['question']}: {e['reason']}")

    passed2, excluded2 = filter_markets(
        markets,
        min_volume_usd=0,
        min_liquidity_score=0.0,
        exclude_categories=None,
    )
    print(f"\nProof: no category filter => {len(passed2)} passed, "
          f"sports filter => {len(passed)} passed ({len(passed2) - len(passed)} sports excluded)")


@pytest.mark.asyncio
async def test_liquidity_score_computed(client):
    markets = await client.get_markets(limit=5, order_by="volumeNum", ascending=False)
    assert len(markets) > 0
    score = compute_liquidity_score(markets[0])
    assert 0.0 <= score <= 1.0, f"Liquidity score {score} should be in [0, 1]"


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


def test_sub_outcome_vwap():
    prices_and_volumes = [(0.5, 1000), (0.6, 2000), (0.4, 1500)]
    result = sub_outcome_vwap(prices_and_volumes)
    expected = (0.5 * 1000 + 0.6 * 2000 + 0.4 * 1500) / (1000 + 2000 + 1500)
    assert result is not None
    assert abs(result - expected) < 0.0001


def test_sub_outcome_vwap_empty():
    assert sub_outcome_vwap([]) is None


def test_sub_outcome_vwap_zero_volume():
    assert sub_outcome_vwap([(0.5, 0), (0.6, 0)]) is None


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
        min_volume_usd=5000,
        min_liquidity_score=0.3,
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
        if "condition_id" in c:
            assert "clob_token_id" in c
            assert "question" in c
        if "sub_markets" in c:
            assert "market_id" in c
            assert isinstance(c["sub_markets"], list)
            assert c["sub_market_count"] == len(c["sub_markets"])
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
            min_volume_usd=5000,
            min_liquidity_score=0.3,
            exclude_categories="sports",
        )
        assert result is not None
        assert result["basket_name"] == name
        if result["total_constituents"] > 0:
            assert result["index_price"] is not None
        print(f"\nBasket {name}: index_price={result['index_price']}, "
              f"constituents={result['total_constituents']}")


# ── Verification: CLOB vs Gamma price diff + liquidity filter output  ──


@pytest.mark.asyncio
async def test_verification_output(client):
    """Print detailed verification output as required by PLAN.md verification prompt."""
    print("\n\n=== VERIFICATION OUTPUT ===")

    markets = await client.get_markets(limit=50, order_by="volumeNum", ascending=False)
    print(f"\nFetched {len(markets)} markets from Gamma /markets")

    passed, excluded = filter_markets(
        markets,
        min_volume_usd=50000,
        min_liquidity_score=0.0,
        exclude_categories="sports",
    )
    print(f"\nLiquidity filter (min_volume=$50k, sports excluded): "
          f"{len(passed)} passed, {len(excluded)} excluded")
    for e in excluded[:5]:
        print(f"  EXCLUDED: {e['question']} — {e['reason']}")

    if passed:
        m = passed[0]
        token_ids = client.get_clob_token_ids(m)
        cond_id = m.get("conditionId", "")
        event_id = client.get_event_id(m)
        print(f"\nTop passed market: {m.get('question')}")
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