"""Local-only evidence tests: passing means current unsafe behavior reproduced.

These are not safety regressions. Replace unsafe-behavior assertions when
the corresponding design/fix has been approved and implemented. No RPC or
hosted API calls, real credentials, or real signing keys are used.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from xleuth_matching.api import create_app
from xleuth_matching.orderbook import BasketOrderBook, OrderRecord, OrderType, Side
from xleuth_matching.settlement import SettlementBridge

from .test_api import (
    ALICE,
    AUTH_ALICE,
    AUTH_BOB,
    BOB,
    FakeChain,
    FakeSubmitter,
    MockInternalVerifier,
    make_client,
    make_config,
)


BASKET = "TOP20-JANUARY-2027"


def _order(side="buy", **fields):
    return {
        "basket_name": BASKET,
        "side": side,
        "price": 50.0,
        "size": 100.0,
        "leverage": 5,
        **fields,
    }


def test_evidence_missing_settlement_legs_are_confirmed_without_transactions():
    config = replace(make_config(), trader_keys={})
    submitter = FakeSubmitter()
    bridge = SettlementBridge(config, submitter=submitter)
    chain = FakeChain()
    app = create_app(config, chain=chain, bridge=bridge)
    chain_id = "0x" + "01" * 32
    app.state.engine.attach_registry(
        {BASKET: {
            "status": "active",
            "expiry_at": datetime.fromtimestamp(chain._settlement_expiry, timezone.utc),
            "onchain_index_id": chain_id,
        }},
        {BASKET: chain_id},
    )
    app.state.engine.internal_verifier = MockInternalVerifier()
    client = TestClient(app)

    client.post("/orders", json=_order(), headers=AUTH_ALICE)
    response = client.post("/orders", json=_order("sell"), headers=AUTH_BOB)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "filled"
    assert body["fills"][0]["confirmed"] is True
    assert body["fills"][0]["tx_hash"] is None
    assert submitter.calls == []


def test_evidence_concurrent_idempotency_key_can_create_two_orders():
    barrier = Barrier(2)

    class ConcurrentChain(FakeChain):
        def free_balance(self, wallet):
            # Both sync endpoints passed check_idempotency before either
            # placement is allowed to complete.
            barrier.wait(timeout=10)
            return super().free_balance(wallet)

    client = make_client(chain=ConcurrentChain())
    headers = {**AUTH_ALICE, "Idempotency-Key": "local-security-review-intent"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(client.post, "/orders", json=_order(), headers=headers)
            for _ in range(2)
        ]
        responses = [future.result(timeout=15) for future in futures]

    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["order_id"] for response in responses}) == 2


def test_evidence_triggering_a_stop_mutates_the_iterated_dictionary():
    book = BasketOrderBook(BASKET)
    book.place_stop(
        OrderRecord(
            order_id="local-stop",
            basket_name=BASKET,
            trader=ALICE,
            side=Side.BUY,
            price=0,
            size=100,
            leverage=5,
            order_type=OrderType.STOP,
            trigger_price=50,
            max_slippage_bps=100,
        )
    )
    with pytest.raises(RuntimeError, match="dictionary changed size during iteration"):
        book.check_triggers(50)


def test_evidence_resting_orders_do_not_reserve_margin():
    client = make_client(chain=FakeChain(free=1_000))
    first = client.post("/orders", json=_order(price=40), headers=AUTH_ALICE)
    second = client.post("/orders", json=_order(price=40), headers=AUTH_ALICE)
    # Each order independently requires all 1,000 USDC of available margin.
    assert first.status_code == second.status_code == 201
    assert first.json()["status"] == second.json()["status"] == "open"


def test_evidence_sltp_accepts_an_arbitrary_position_identifier():
    client = make_client(chain=FakeChain(position=(0, 100, 5)))
    response = client.post(
        "/orders",
        json={
            "basket_name": BASKET,
            "order_type": "stop_loss",
            "trigger_price": 40,
            "max_slippage_bps": 100,
            "position_id": "not-the-authenticated-wallets-position",
        },
        headers=AUTH_ALICE,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "open"


def test_evidence_one_failed_leg_does_not_undo_the_other_submission():
    submitter = FakeSubmitter(fail_wallet=BOB)
    client = make_client(submitter=submitter)
    client.post("/orders", json=_order(), headers=AUTH_ALICE)
    response = client.post("/orders", json=_order("sell"), headers=AUTH_BOB)
    assert response.json()["status"] == "rejected"
    # The synthetic successful ALICE submission is not rolled back when BOB
    # reverts. This proves independent legs, not actual hosted-chain damage.
    assert {update.wallet for update in submitter.calls} == {ALICE, BOB}
