"""Integration: register idempotency + service pickup with no redeploy (fakes, no network)."""
from datetime import datetime, timedelta, timezone
from functools import partial

import pytest

from xleuth_matching.margin_check import ChainState, MarginCheck
from xleuth_shared.baskets import basket_id_from_slug


def _future(days=30):
    return datetime.now(timezone.utc) + timedelta(days=days)


class FakeChain(ChainState):
    def oracle_price(self, basket_name, index_id_hex=None):
        return (50, int(datetime.now(timezone.utc).timestamp()))

    def free_balance(self, wallet):
        return 10_000_000_000

    def max_leverage(self):
        return 5

    def position_size(self, wallet, basket_name):
        return 0

    def get_position(self, wallet, basket_name):
        return None


def _cfg(baskets):
    class C:
        pass
    c = C()
    c.baskets = baskets
    c.max_price_staleness_seconds = 60
    c.price_scale = 100
    c.max_leverage = 5
    c.min_order_size = 10
    c.tick_size = 0.01
    return c


# ── 1. Matching engine picks up a newly activated basket ──────────────

def test_margin_check_db_registry_rejects_non_active_and_accepts_new(monkeypatch):
    from xleuth_matching import margin_check
    from xleuth_shared.basket_lifecycle import is_tradeable

    monkeypatch.setattr(margin_check, "is_tradeable", partial(
        is_tradeable, now=datetime(2026, 10, 18, tzinfo=timezone.utc)))
    cfg = _cfg(["TOP20-OCTOBER"])
    mc = MarginCheck(cfg, FakeChain())
    # env fallback still works pre-backfill
    assert mc.validate("TOP20-OCTOBER", "0xabc", "buy", 50.0, 10.0, 5).ok

    # DB registry populated: unknown baskets rejected even if env knew others
    rows = {
        "TOP20-OCTOBER": {"name": "TOP20-OCTOBER", "status": "active",
                          "expiry_at": _future(), "onchain_index_id": "0x" + "11" * 32},
        "CRYPTO5-NOVEMBER": {"name": "CRYPTO5-NOVEMBER", "status": "active",
                             "expiry_at": _future(), "onchain_index_id": "0x" + "22" * 32},
    }
    mc.registry = rows
    mc.index_ids = {k: v["onchain_index_id"] for k, v in rows.items()}
    # newly activated custom-theme basket accepted with no restart
    assert mc.validate("CRYPTO5-NOVEMBER", "0xabc", "buy", 50.0, 10.0, 5).ok
    # non-active rejected
    rows["CRYPTO5-NOVEMBER"]["status"] = "closed"
    r = mc.validate("CRYPTO5-NOVEMBER", "0xabc", "buy", 50.0, 10.0, 5)
    assert not r.ok and r.reason == "basket_not_tradeable"
    # expired rejected
    rows["CRYPTO5-NOVEMBER"]["status"] = "active"
    rows["CRYPTO5-NOVEMBER"]["expiry_at"] = datetime.now(timezone.utc) - timedelta(days=1)
    r = mc.validate("CRYPTO5-NOVEMBER", "0xabc", "buy", 50.0, 10.0, 5)
    assert not r.ok and r.reason == "basket_not_tradeable"


def test_engine_attach_registry_creates_books():
    from xleuth_matching.api import Engine

    eng = Engine.__new__(Engine)
    from xleuth_matching.config import MatchingConfig
    import dataclasses
    eng.config = MatchingConfig(
        rpc_url="http://localhost:8545", vault_address="0x" + "01" * 20,
        position_manager_address="0x" + "02" * 20,
        oracle_consumer_address="0x" + "03" * 20, jwt_secret="t",
        chain_id=80002, price_scale=100, max_leverage=5, min_order_size=10,
        tick_size=0.01, trading_fee_bps=10, max_price_staleness_seconds=60,
        baskets=["TOP20-OCTOBER"])
    eng.chain = FakeChain()
    eng.margin = MarginCheck(eng.config, eng.chain)
    from xleuth_matching.orderbook import OrderBookManager
    eng.books = OrderBookManager(eng.config.baskets)
    eng.registry = None
    eng.index_ids = {}
    assert eng.known_baskets == ["TOP20-OCTOBER"]
    eng.attach_registry({"CRYPTO5-NOVEMBER": {"name": "CRYPTO5-NOVEMBER",
                                              "status": "active", "expiry_at": _future()}},
                        {"CRYPTO5-NOVEMBER": "0x" + "22" * 32})
    assert "CRYPTO5-NOVEMBER" in eng.known_baskets
    assert eng.book("CRYPTO5-NOVEMBER") is not None


# ── 2. Oracle discovers DB baskets, skips rows without index id ───────

@pytest.mark.asyncio
async def test_oracle_discover_prefers_db_and_skips_unregistered():
    from xleuth_oracle import basket_source

    basket_source.clear_cache()

    class Cfg:
        baskets = ["TOP20-OCTOBER"]

    async def fake_list_active(pool, now=None):
        return [
            {"name": "TOP20-NOVEMBER", "onchain_index_id": "0x" + "aa" * 32,
             "expiry_at": _future(), "status": "active"},
            {"name": "DRAFT-ONE", "onchain_index_id": None,
             "expiry_at": _future(), "status": "draft"},
        ]

    import xleuth_shared.db_baskets as dbb
    real = dbb.list_active
    dbb.list_active = fake_list_active
    try:
        items = await basket_source.discover_baskets(Cfg(), pool=object(), force=True)
        names = [i["name"] for i in items]
        assert "TOP20-NOVEMBER" in names  # DB active picked up, no restart
        assert "DRAFT-ONE" not in names  # no onchain id -> skipped
        assert "TOP20-OCTOBER" in names  # env fallback fills the gap
        # TTL: second call without force returns cached object
        assert await basket_source.discover_baskets(Cfg(), pool=None) is items
    finally:
        dbb.list_active = real
        basket_source.clear_cache()


# ── 3. Ingestion discovers DB + env without double-processing ─────────

@pytest.mark.asyncio
async def test_ingestion_discover_db_wins_over_env():
    from xleuth_ingestion import poller

    async def fake_list_active(pool, now=None):
        return [{"name": "TOP20-OCTOBER", "slug": "top20-2026-10",
                 "market_count": 20, "window_start": datetime(2026, 10, 1, tzinfo=timezone.utc),
                 "expiry_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
                 "selection_rules": {"exclude_categories": "sports"}, "status": "active"}]

    import xleuth_shared.db_baskets as dbb
    real = dbb.list_active
    dbb.list_active = fake_list_active
    try:
        config = {"active_baskets": ["TOP20-{MONTH}"], "exclude_categories": "sports"}
        items, _ = await poller.discover_work_items(config, pool=object())
        by_name = {i["basket_name"]: i for i in items}
        # DB row wins for OCTOBER (source=db, explicit params, no name parse)
        assert by_name["TOP20-OCTOBER"]["source"] == "db"
        assert by_name["TOP20-OCTOBER"]["market_count"] == 20
    finally:
        dbb.list_active = real


# ── 4. Register flow: adopt-when-exists is idempotent ─────────────────

def test_register_adopts_existing_index_without_second_tx():
    slug = "top20-2026-11"
    index_id = "0x" + basket_id_from_slug(slug).hex()
    intended_expiry = 1764547199

    class FakeChainReg:
        def __init__(self, existing):
            self.existing = existing
            self.sent = []

        def get_expiry(self, idx):
            return self.existing.get(idx, 0)

        def send_set_expiry(self, idx, expiry):
            self.sent.append((idx, expiry))
            return "0xtx"

    # already registered with same expiry -> adopt, no tx
    chain = FakeChainReg({index_id: intended_expiry})
    assert chain.get_expiry(index_id) == intended_expiry
    assert chain.sent == []
    # different expiry -> must send
    chain2 = FakeChainReg({index_id: 1})
    assert chain2.get_expiry(index_id) != intended_expiry


def test_signing_override_matches_db_index_id():
    from xleuth_oracle.signing import basket_id_from_name, sign_price_update

    slug = "top20-2026-11"
    index_id = "0x" + basket_id_from_slug(slug).hex()
    key = "0x" + "ab" * 32
    s1 = sign_price_update(key, "0x" + "11" * 20, 80002, "TOP20-NOVEMBER", 50, 123, index_id_override=index_id)
    s2 = sign_price_update(key, "0x" + "11" * 20, 80002, "TOP20-NOVEMBER", 50, 123,
                           index_id_override=basket_id_from_slug(slug))
    assert s1 == s2
    s3 = sign_price_update(key, "0x" + "11" * 20, 80002, "TOP20-NOVEMBER", 50, 123)
    assert s3 != s1  # legacy keccak(NAME) differs from keccak(slug) by design
