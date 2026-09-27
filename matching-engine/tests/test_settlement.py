import pytest

from xleuth_matching.config import MatchingConfig
from xleuth_matching.orderbook import Fill, Side
from xleuth_matching.settlement import SettlementBridge, TxSubmitter

ALICE = "0x1111111111111111111111111111111111111111"
BOB = "0x2222222222222222222222222222222222222222"
CAROL = "0x3333333333333333333333333333333333333333"


class FakeSubmitter(TxSubmitter):
    def __init__(self, receipts=None, raises=None):
        self.calls: list = []
        self._receipts = receipts or {}
        self._raises = raises or {}

    def submit(self, update):
        self.calls.append(update)
        if update.wallet in self._raises:
            raise self._raises[update.wallet]
        receipt = self._receipts.get(update.wallet, {"status": 1})
        return f"0x{update.wallet[-4:]}{len(self.calls)}", receipt


def make_config() -> MatchingConfig:
    return MatchingConfig(
        rpc_url="http://localhost:8545",
        vault_address="0x0000000000000000000000000000000000000001",
        position_manager_address="0x0000000000000000000000000000000000000002",
        oracle_consumer_address="0x0000000000000000000000000000000000000003",
        dynamic_environment_id="test-env-id",
        chain_id=80002,
        price_scale=100,
        max_leverage=5,
        min_order_size=10,
        tick_size=0.01,
        trading_fee_bps=10,
        max_price_staleness_seconds=60,
        baskets=["TOP20-SEPTEMBER"],
        trader_keys={ALICE: "0x" + "a" * 64, BOB: "0x" + "b" * 64},
    )


def make_fill(size, taker=ALICE, maker=BOB, taker_side=Side.BUY, price=50.0,
              taker_lev=5, maker_lev=5, basket="TOP20-SEPTEMBER", trade_id=None):
    return Fill(
        trade_id=trade_id or f"t{size}{taker[-2:]}{maker[-2:]}",
        basket_name=basket,
        price=price,
        size=size,
        timestamp=__import__("datetime").datetime.now(),
        taker_order_id="taker",
        maker_order_id="maker",
        taker_trader=taker,
        maker_trader=maker,
        taker_side=taker_side,
        maker_side=taker_side.opposite(),
        taker_leverage=taker_lev,
        maker_leverage=maker_lev,
    )


def settle(fills, **kw):
    submitter = FakeSubmitter(**kw)
    bridge = SettlementBridge(make_config(), submitter=submitter)
    return bridge.settle_fills(fills), submitter


def test_single_fill_settles_both_sides():
    outcomes, submitter = settle([make_fill(100.0)])
    assert len(outcomes) == 2
    assert len(submitter.calls) == 2
    by_wallet = {o.update.wallet: o for o in outcomes}
    assert all(o.ok and o.tx_hash and o.mined_at for o in outcomes)
    assert by_wallet[ALICE].update.side is Side.BUY
    assert by_wallet[ALICE].update.size == 100.0
    assert by_wallet[ALICE].update.size_int == 100
    assert by_wallet[ALICE].update.leverage == 5
    assert by_wallet[BOB].update.side is Side.SELL
    assert by_wallet[BOB].update.basket_name == "TOP20-SEPTEMBER"


def test_same_trader_both_sides_nets_to_one_update():
    # Alice buys 100 and sells 40 on the same basket: one net +60 long tx.
    fill1 = make_fill(100.0, taker=ALICE, maker=BOB, taker_side=Side.BUY)
    fill2 = make_fill(40.0, taker=BOB, maker=ALICE, taker_side=Side.BUY)  # alice sells 40
    outcomes, submitter = settle([fill1, fill2])
    alice_updates = [o for o in outcomes if o.update.wallet == ALICE]
    assert len(alice_updates) == 1
    assert alice_updates[0].update.side is Side.BUY
    assert alice_updates[0].update.size == 60.0
    assert len(submitter.calls) == 2  # alice netted + bob


def test_net_zero_fills_skip_onchain():
    # Alice buys 100 (fill1) then sells 100 (fill2, as maker): net zero both sides.
    fill1 = make_fill(100.0, taker=ALICE, maker=BOB, taker_side=Side.BUY)
    fill2 = make_fill(100.0, taker=BOB, maker=ALICE, taker_side=Side.BUY)
    outcomes, submitter = settle([fill1, fill2])
    assert outcomes == []
    assert submitter.calls == []


def test_dust_net_skipped():
    # Alice buys 100, sells 99.8 -> net 0.2 rounds to zero: nothing on-chain.
    fill1 = make_fill(100.0, taker=ALICE, maker=BOB, taker_side=Side.BUY)
    fill2 = make_fill(99.8, taker=BOB, maker=ALICE, taker_side=Side.BUY)
    outcomes, submitter = settle([fill1, fill2])
    assert outcomes == []
    assert submitter.calls == []


def test_revert_surfaces_failure_with_tx_hash():
    outcomes, _ = settle(
        [make_fill(100.0)], receipts={ALICE: {"status": 0}, BOB: {"status": 1}}
    )
    by_wallet = {o.update.wallet: o for o in outcomes}
    assert not by_wallet[ALICE].ok
    assert "reverted" in by_wallet[ALICE].error
    assert by_wallet[ALICE].tx_hash
    assert by_wallet[BOB].ok


def test_submitter_raise_surfaces_error():
    outcomes, _ = settle(
        [make_fill(100.0)], raises={BOB: ValueError("no private key configured for trader x")}
    )
    by_wallet = {o.update.wallet: o for o in outcomes}
    assert by_wallet[ALICE].ok
    assert not by_wallet[BOB].ok
    assert "no private key configured" in by_wallet[BOB].error


def test_untracked_trader_leg_skipped_without_crash():
    fill = make_fill(100.0, taker=ALICE, maker=CAROL)
    outcomes, submitter = settle([fill])
    assert len(outcomes) == 1
    assert outcomes[0].update.wallet == ALICE
    assert len(submitter.calls) == 1


def test_leverage_is_volume_weighted_mean():
    # alice: lev 5 @ 100, then lev 2 @ 100 -> weighted 3.5 -> round 4
    fill1 = make_fill(100.0, taker=ALICE, maker=BOB, taker_side=Side.BUY, taker_lev=5, maker_lev=5)
    fill2 = make_fill(100.0, taker=ALICE, maker=BOB, taker_side=Side.BUY, taker_lev=2, maker_lev=2)
    outcomes, _ = settle([fill1, fill2])
    alice = [o for o in outcomes if o.update.wallet == ALICE][0]
    assert alice.update.leverage == 4
    assert alice.update.size == 200.0
    bob = [o for o in outcomes if o.update.wallet == BOB][0]
    assert bob.update.leverage == 4
    assert bob.update.size == 200.0


def test_empty_fills_returns_empty():
    outcomes, submitter = settle([])
    assert outcomes == []
    assert submitter.calls == []