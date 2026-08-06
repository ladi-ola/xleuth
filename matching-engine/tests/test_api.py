import time
from datetime import datetime

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from xleuth_matching.api import create_app
from xleuth_matching.config import MatchingConfig
from xleuth_matching.margin_check import ChainState
from xleuth_matching.settlement import SettlementBridge, TxSubmitter

ALICE = "0x" + "a" * 40
BOB = "0x" + "b" * 40


def _now() -> int:
    return int(time.time())


class FakeChain(ChainState):
    def __init__(self, oracle=(50, None), free=100_000.0, max_lev=5):
        self.oracle = (oracle[0], oracle[1] if oracle[1] is not None else _now())
        self.free = int(free * 1e6)
        self.max_lev = max_lev

    def oracle_price(self, basket_name):
        return self.oracle

    def free_balance(self, wallet):
        return self.free

    def max_leverage(self):
        return self.max_lev

    def position_size(self, wallet, basket_name):
        return 0


class FakeSubmitter(TxSubmitter):
    def __init__(self, fail_wallet: str | None = None):
        self.calls = []
        self.fail_wallet = fail_wallet

    def submit(self, update):
        self.calls.append(update)
        status = 0 if update.wallet == self.fail_wallet else 1
        return f"0xtx{len(self.calls):04d}", {"status": status}


def make_config() -> MatchingConfig:
    return MatchingConfig(
        rpc_url="http://localhost:8545",
        vault_address="0x" + "0" * 40,
        position_manager_address="0x" + "1" * 40,
        oracle_consumer_address="0x" + "2" * 40,
        jwt_secret="test-secret",
        chain_id=80002,
        price_scale=100,
        max_leverage=5,
        min_order_size=10,
        tick_size=0.01,
        trading_fee_bps=10,
        max_price_staleness_seconds=60,
        baskets=["TOP20-AUGUST", "TOP20-SEPTEMBER"],
        trader_keys={ALICE: "0x" + "a" * 64, BOB: "0x" + "b" * 64},
    )


def make_client(chain: ChainState | None = None, submitter: TxSubmitter | None = None):
    app = create_app(make_config(), chain=chain or FakeChain(), bridge=SettlementBridge(make_config(), submitter=submitter or FakeSubmitter()))
    return TestClient(app)


def token(wallet: str, secret: str = "test-secret") -> str:
    return pyjwt.encode({"sub": wallet, "exp": datetime.utcnow().timestamp() + 3600}, secret, algorithm="HS256")


AUTH_ALICE = {"Authorization": f"Bearer {token(ALICE)}"}
AUTH_BOB = {"Authorization": f"Bearer {token(BOB)}"}


def test_requires_bearer_token():
    client = make_client()
    resp = client.post("/orders", json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5})
    assert resp.status_code == 401


def test_rejects_bad_token():
    client = make_client()
    bad = {"Authorization": "Bearer not.a.token"}
    resp = client.post("/orders", json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5}, headers=bad)
    assert resp.status_code == 401


def test_rejects_insufficient_margin_with_code_path_reason():
    client = make_client(chain=FakeChain(free=10.0))
    resp = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    )
    assert resp.status_code == 422
    assert "insufficient_margin" in resp.json()["detail"]


def test_rejects_stale_oracle():
    client = make_client(chain=FakeChain(oracle=(50, _now() - 120)))
    resp = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    )
    assert resp.status_code == 422
    assert "oracle_price_stale" in resp.json()["detail"]


def test_rejects_unknown_basket():
    client = make_client()
    resp = client.post(
        "/orders",
        json={"basket_name": "TOP20-UNKNOWN", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    )
    assert resp.status_code == 422
    assert "unknown_basket" in resp.json()["detail"]


def test_resting_order_then_cancel():
    client = make_client()
    resp = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 40.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["fills"] == []
    order_id = body["order_id"]

    resp = client.delete(f"/orders/{order_id}", headers=AUTH_ALICE)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    resp = client.get(f"/orders/{order_id}", headers=AUTH_ALICE)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_crossing_orders_match_and_fills_confirmed_with_tx():
    client = make_client()
    alice = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    ).json()
    bob = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "sell", "price": 49.0, "size": 100.0, "leverage": 5},
        headers=AUTH_BOB,
    ).json()

    # The match happens on the taker's placement (bob); alice's resting order
    # is marked filled in the registry.
    assert bob["status"] == "filled"
    fills = bob["fills"]
    assert len(fills) == 1
    assert fills[0]["confirmed"] is True
    assert fills[0]["tx_hash"].startswith("0xtx")
    assert fills[0]["maker_order_id"] == alice["order_id"]
    assert bob["failed_fills"] == []

    alice_after = client.get(f"/orders/{alice['order_id']}", headers=AUTH_ALICE).json()
    assert alice_after["status"] == "filled"
    assert alice_after["filled_size"] == 100.0


def test_revert_onchain_leaves_fill_unconfirmed_and_order_rejected():
    client = make_client(submitter=FakeSubmitter(fail_wallet=BOB))
    alice = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 50.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    ).json()
    bob = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "sell", "price": 49.0, "size": 100.0, "leverage": 5},
        headers=AUTH_BOB,
    ).json()

    assert bob["failed_fills"][0]["confirmed"] is False
    assert bob["failed_fills"][0]["error"]
    assert bob["status"] == "rejected"
    assert "settlement failed" in (bob["rejection_reason"] or "")

    alice_after = client.get(f"/orders/{alice['order_id']}", headers=AUTH_ALICE).json()
    assert alice_after["status"] == "rejected"
    assert "settlement failed" in (alice_after["rejection_reason"] or "")


def test_cannot_cancel_someone_elses_order():
    client = make_client()
    order = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 40.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    ).json()
    resp = client.delete(f"/orders/{order['order_id']}", headers=AUTH_BOB)
    assert resp.status_code == 403


def test_book_depth_snapshot():
    client = make_client()
    client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 40.0, "size": 100.0, "leverage": 5},
        headers=AUTH_ALICE,
    )
    client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "sell", "price": 60.0, "size": 100.0, "leverage": 5},
        headers=AUTH_BOB,
    )
    resp = client.get("/baskets/TOP20-AUGUST/book")
    assert resp.status_code == 200
    body = resp.json()
    assert body["best_bid"] == 40.0
    assert body["best_ask"] == 60.0
    assert body["spread"] == 20.0
