"""Offline transport tests; signature/execution semantics are tested in Foundry.

RPC and ledger receipts below are explicit test doubles, not live-settlement
evidence. No real network, account secrets or on-chain transactions are used.
"""

from dataclasses import replace

import pytest
from eth_account import Account
from eth_utils import keccak
from eth_abi import encode
from eth_account.messages import encode_typed_data
from web3 import Web3

from xleuth_matching.relayed_execution import (
    AtomicRelaySubmitter,
    AuthorizedMatch,
    RelayPending,
    RelayReverted,
)
from xleuth_shared.trade_authorization import AUTHORIZATION_FIELDS, TradeAuthorization, notional_units

EXECUTOR = "0x" + "22" * 20
RELAYER_KEY = "0x" + "12" * 32  # Synthetic local key, never used on hosted APIs.


def matched(**overrides):
    buy_intent, sell_intent = b"synthetic buy intent", b"synthetic sell intent"
    common = dict(
        basket_id="0x" + "aa" * 32, size=200_000, max_notional=10_000_000,
        min_price=50_000, max_price=50_000, leverage=5, nonce=7, deadline=2_000_000_000,
    )
    buy = TradeAuthorization(trader="0x" + "11" * 20, order_id="0x" + keccak(buy_intent).hex(), side=0, **common)
    sell = TradeAuthorization(trader="0x" + "33" * 20, order_id="0x" + keccak(sell_intent).hex(), side=1, **common)
    base = AuthorizedMatch(buy, b"\x12\x34", sell, b"\x56\x78", 200_000, 50_000, buy_intent, sell_intent)
    return replace(base, **overrides)


class FakeEth:
    chain_id = 80002

    def __init__(self):
        self.payloads = []
        self.raws = []
        self.has_code = True
        self.receipt = {"status": 1, "blockNumber": 7}
        self.timeout = False
        self.send_timeout = False
        self.preflight_error = None
        self.nonce_requests = []

    def get_code(self, address):
        return b"\x60" if self.has_code else b""

    def get_transaction_count(self, address, state):
        self.nonce_requests.append((address, state))
        return 0

    def contract(self, *, address, abi):
        eth = self

        class Executor:
            def __init__(self):
                self.address = address
                self.functions = self
                self.events = Web3().eth.contract(address=address, abi=abi).events

            def executeMatches(self, payload):
                eth.payloads.append(payload)

                class Call:
                    def build_transaction(self, transaction):
                        if eth.preflight_error:
                            raise eth.preflight_error
                        encoder = Web3().eth.contract(address=address, abi=abi)
                        return {
                            **transaction, "to": address, "gas": 350_000,
                            "gasPrice": 1_000_000_000, "value": 0,
                            "data": encoder.encode_abi("executeMatches", args=[payload]),
                        }

                return Call()

        return Executor()

    def send_raw_transaction(self, raw):
        self.raws.append(raw)
        if self.send_timeout:
            raise TimeoutError("synthetic disconnect after accepting tx")
        return Web3.keccak(raw)

    def wait_for_transaction_receipt(self, tx_hash, timeout):
        if self.timeout:
            raise TimeoutError("synthetic receipt timeout")
        return self.completed_receipt()

    def get_transaction_receipt(self, tx_hash):
        return self.completed_receipt()

    def completed_receipt(self):
        if "logs" in self.receipt:
            return self.receipt

        def digest(values):
            message = encode_typed_data(
                domain_data={"name": "Xleuth Orders", "version": "2", "chainId": 80002,
                             "verifyingContract": EXECUTOR},
                message_types={"Authorization": AUTHORIZATION_FIELDS},
                message_data=dict(zip((f["name"] for f in AUTHORIZATION_FIELDS), values)),
            )
            return keccak(b"\x19" + message.version + message.header + message.body)

        logs = []
        for index, payload in enumerate(self.payloads[-1]):
            buy, _, sell, _, size, price, _, _ = payload
            logs.append({
                "address": Web3.to_checksum_address(EXECUTOR),
                "topics": [keccak(text="MatchExecuted(bytes32,bytes32,bytes32,uint256,uint256,uint256)"),
                           digest(buy), digest(sell), bytes.fromhex(buy[1][2:])],
                "data": encode(["uint256", "uint256", "uint256"], [size, price, notional_units(size, price)]),
                "blockNumber": 7, "transactionHash": Web3.keccak(self.raws[-1]),
                "transactionIndex": 0, "logIndex": index, "blockHash": b"\xaa" * 32,
            })
        return {"transactionHash": Web3.keccak(self.raws[-1]), **self.receipt, "logs": logs}


class FakeWeb3:
    is_address = staticmethod(Web3.is_address)
    to_checksum_address = staticmethod(Web3.to_checksum_address)
    to_hex = staticmethod(Web3.to_hex)
    keccak = staticmethod(Web3.keccak)

    def __init__(self):
        self.eth = FakeEth()


class TestJournal:
    __test__ = False

    def __init__(self):
        self.current = None
        self.receipts = []
        self.fail_write = False
        self.fail_receipt = False

    def pending(self, chain_id, relayer):
        return self.current

    def record_signed(self, chain_id, relayer, pending):
        if self.fail_write or self.current is not None:
            raise ValueError("journal write failed or slot already reserved")
        self.current = pending

    def record_receipt(self, chain_id, relayer, tx_hash, receipt):
        if self.fail_receipt:
            raise ValueError("journal receipt write failed")
        assert self.current.tx_hash == tx_hash
        self.receipts.append(receipt)
        self.current = None


def submitter():
    w3 = FakeWeb3()
    return AtomicRelaySubmitter(
        w3=w3, executor_address=EXECUTOR, chain_id=80002,
        relayer_private_key=RELAYER_KEY, journal=TestJournal(),
    ), w3.eth


def test_one_relayer_transaction_contains_both_trader_authorizations():
    relay, eth = submitter()
    result = relay.submit([matched()])
    assert result.match_count == 1
    assert result.block_number == 7
    assert len(eth.raws) == 1
    assert len(eth.payloads[0]) == 1
    assert eth.payloads[0][0][0][0] == matched().buy.trader
    assert eth.payloads[0][0][2][0] == matched().sell.trader
    assert Account.recover_transaction(eth.raws[0]) == Account.from_key(RELAYER_KEY).address
    assert eth.nonce_requests[0][1] == "pending"


def test_multiple_makers_are_in_one_transaction_not_separate_trader_legs():
    relay, eth = submitter()
    first = matched()
    buy = replace(first.buy, size=400_000, max_notional=20_000_000, fill_or_kill=True)
    second_intent = b"synthetic second maker"
    second_sell = replace(
        first.sell, trader="0x" + "44" * 20, nonce=8,
        order_id="0x" + keccak(second_intent).hex(),
    )
    relay.submit([
        replace(first, buy=buy),
        replace(first, buy=buy, sell=second_sell, sell_intent=second_intent),
    ])
    assert len(eth.raws) == 1
    assert len(eth.payloads[0]) == 2


def test_reverted_receipt_never_becomes_a_confirmation():
    relay, eth = submitter()
    eth.receipt = {"status": 0, "blockNumber": 7}
    with pytest.raises(RelayReverted):
        relay.submit([matched()])


@pytest.mark.parametrize("receipt", [{}, {"status": 1}, {"status": True, "blockNumber": 7}])
def test_missing_or_malformed_receipt_is_not_success(receipt):
    relay, eth = submitter()
    eth.receipt = receipt
    with pytest.raises(RelayPending):
        relay.submit([matched()])


def test_receipt_timeout_latches_hash_and_requires_reconciliation_not_resubmission():
    relay, eth = submitter()
    eth.timeout = True
    with pytest.raises(RelayPending) as first:
        relay.submit([matched()])
    with pytest.raises(RelayPending) as second:
        relay.submit([matched()])
    assert first.value.tx_hash == second.value.tx_hash
    assert len(eth.raws) == 1
    result = relay.reconcile_pending()
    assert result.tx_hash == first.value.tx_hash
    assert result.match_count == 1


def test_broadcast_disconnect_also_has_a_known_hash_and_never_auto_resubmits():
    relay, eth = submitter()
    eth.send_timeout = True
    with pytest.raises(RelayPending) as pending:
        relay.submit([matched()])
    assert pending.value.tx_hash == Web3.to_hex(Web3.keccak(eth.raws[0]))
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    assert len(eth.raws) == 1
    assert relay.reconcile_pending().tx_hash == pending.value.tx_hash


def test_preflight_failure_sends_nothing_and_has_no_trader_key_fallback():
    relay, eth = submitter()
    eth.preflight_error = ValueError("financial ledger not configured")
    with pytest.raises(ValueError, match="ledger"):
        relay.submit([matched()])
    assert not eth.raws


def test_wrong_chain_or_missing_executor_code_sends_nothing():
    relay, eth = submitter()
    eth.chain_id = 1
    with pytest.raises(ValueError, match="wrong chain"):
        relay.submit([matched()])
    eth.chain_id = 80002
    eth.has_code = False
    with pytest.raises(ValueError, match="deployed code"):
        relay.submit([matched()])
    assert not eth.raws


def test_invalid_intent_preimage_rejected_before_transport():
    with pytest.raises(ValueError, match="preimage"):
        matched(buy_intent=b"changed trigger or OCO payload")


@pytest.mark.parametrize("changes", [{"size": 0}, {"size": 200_001}, {"price": 50_001}, {"size": True}])
def test_fill_cannot_change_signed_bounds(changes):
    with pytest.raises(ValueError):
        matched(**changes)


def test_self_trade_and_cross_basket_rejected_before_transport():
    m = matched()
    with pytest.raises(ValueError, match="self-trade"):
        replace(m, sell=replace(m.sell, trader=m.buy.trader))
    with pytest.raises(ValueError, match="basket"):
        replace(m, sell=replace(m.sell, basket_id="0x" + "bb" * 32))


def test_empty_batch_rejected_without_signing_or_broadcast():
    relay, eth = submitter()
    with pytest.raises(ValueError, match="empty"):
        relay.submit([])
    assert not eth.raws


def test_journal_failure_prevents_broadcast():
    relay, eth = submitter()
    relay._journal.fail_write = True
    with pytest.raises(ValueError, match="journal"):
        relay.submit([matched()])
    assert not eth.raws


def test_mined_transaction_with_failed_journal_write_remains_pending():
    relay, eth = submitter()
    relay._journal.fail_receipt = True
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    assert relay._journal.current is not None
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    assert len(eth.raws) == 1


@pytest.mark.parametrize("status", [0, 1])
def test_foreign_receipt_cannot_clear_a_pending_transaction(status):
    relay, eth = submitter()
    eth.timeout = True
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    eth.receipt = {**eth.completed_receipt(), "transactionHash": b"\xff" * 32, "status": status}
    with pytest.raises(RelayPending):
        relay.reconcile_pending()
    assert relay._journal.current is not None
    assert relay._journal.receipts == []


def test_reconciliation_on_a_different_chain_keeps_the_journal_pending():
    relay, eth = submitter()
    eth.timeout = True
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    eth.chain_id = 1
    with pytest.raises(RelayPending):
        relay.reconcile_pending()
    assert relay._journal.current is not None
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    assert len(eth.raws) == 1


def test_restart_recovers_pending_transaction_without_rebroadcast():
    relay, eth = submitter()
    eth.timeout = True
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    w3 = FakeWeb3()
    w3.eth.receipt = eth.completed_receipt()
    restarted = AtomicRelaySubmitter(
        w3=w3, executor_address=EXECUTOR, chain_id=80002,
        relayer_private_key=RELAYER_KEY, journal=relay._journal,
    )
    with pytest.raises(RelayPending):
        restarted.submit([matched()])
    assert not w3.eth.raws
    assert restarted.reconcile_pending().tx_hash == Web3.to_hex(Web3.keccak(eth.raws[0]))


def test_no_in_memory_production_journal_fallback():
    with pytest.raises(ValueError, match="journal"):
        AtomicRelaySubmitter(
            w3=FakeWeb3(), executor_address=EXECUTOR, chain_id=80002,
            relayer_private_key=RELAYER_KEY, journal=None,
        )


@pytest.mark.parametrize("change", ["missing", "wrong-executor", "wrong-size"])
def test_receipt_status_one_without_matching_execution_evidence_is_not_confirmed(change):
    relay, eth = submitter()
    eth.timeout = True
    with pytest.raises(RelayPending):
        relay.submit([matched()])
    receipt = eth.completed_receipt()
    if change == "missing":
        receipt["logs"] = []
    elif change == "wrong-executor":
        receipt["logs"][0]["address"] = "0x" + "44" * 20
    else:
        receipt["logs"][0]["data"] = encode(["uint256"] * 3, [1, 50_000, 1])
    eth.receipt = receipt
    with pytest.raises(RelayPending):
        relay.reconcile_pending()
    assert relay._journal.current is not None
