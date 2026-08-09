from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from xleuth_oracle.signing import (
    SETTLE_DOMAIN_NAME,
    SETTLE_DOMAIN_VERSION,
    basket_id_from_name,
    price_to_scale,
    sign_price_update,
    sign_settle_basket,
)

CONTRACT = "0x0000000000000000000000000000000000000001"
KEY = "0x" + "12" * 32


def _typed_data(price: int, ts: int, chain_id: int = 80002):
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "PriceUpdate": [
                {"name": "basketId", "type": "bytes32"},
                {"name": "price", "type": "uint256"},
                {"name": "timestamp", "type": "uint256"},
            ],
        },
        "primaryType": "PriceUpdate",
        "domain": {
            "name": "Xleuth Index Oracle",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": CONTRACT,
        },
        "message": {
            "basketId": "0x" + basket_id_from_name("TOP20-JULY").hex(),
            "price": int(price),
            "timestamp": int(ts),
        },
    }


def test_basket_id_matches_contract_keccak():
    # contracts use `bytes32 basketA = keccak256("TOP20-JULY")`
    assert basket_id_from_name("TOP20-JULY") == keccak(text="TOP20-JULY")
    assert len(basket_id_from_name("TOP20-AUGUST")) == 32


def test_price_to_scale_clamps_and_rounds():
    assert price_to_scale(50.49) == 50
    assert price_to_scale(50.5) == 51
    assert price_to_scale(0.0) == 1
    assert price_to_scale(100.0) == 100
    assert price_to_scale(101.0) == 100


def test_signature_is_65_bytes_r_v():
    sig = sign_price_update(KEY, CONTRACT, 80002, "TOP20-JULY", 50, 1_000_000)
    assert len(sig) == 65
    assert sig[64] in (27, 28)


def test_signature_recovery_matches_signer():
    """Cross-check the signing helper output recovers to the keyholder through
    the exact same EIP-712 reconstruction the Solidity contract performs."""
    account = Account.from_key(KEY)
    price, ts, chain = 55, 1234, 80002
    sig = sign_price_update(KEY, CONTRACT, chain, "TOP20-JULY", price, ts)

    recovered = Account.recover_message(
        encode_typed_data(full_message=_typed_data(price, ts, chain)), signature=sig
    )
    assert recovered.lower() == account.address.lower()


def test_signature_encoding_changes_with_every_field():
    sig1 = sign_price_update(KEY, CONTRACT, 80002, "TOP20-JULY", 50, 100)
    sig2 = sign_price_update(KEY, CONTRACT, 80002, "TOP20-JULY", 50, 101)
    sig3 = sign_price_update(KEY, CONTRACT, 80002, "TOP20-AUGUST", 50, 100)
    assert sig1 != sig2
    assert sig1 != sig3
    assert len(sig1) == len(sig2) == len(sig3) == 65


# ── SettlementEngine SettleBasket signing ────────────────────────────────


def _settle_typed_data(realized: int, ts: int, chain_id: int = 80002):
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "SettleBasket": [
                {"name": "basketId", "type": "bytes32"},
                {"name": "realizedPrice", "type": "uint256"},
                {"name": "timestamp", "type": "uint256"},
            ],
        },
        "primaryType": "SettleBasket",
        "domain": {
            "name": SETTLE_DOMAIN_NAME,
            "version": SETTLE_DOMAIN_VERSION,
            "chainId": chain_id,
            "verifyingContract": CONTRACT,
        },
        "message": {
            "basketId": "0x" + basket_id_from_name("TOP20-JULY").hex(),
            "realizedPrice": int(realized),
            "timestamp": int(ts),
        },
    }


def test_settle_signature_is_65_bytes_r_v():
    sig = sign_settle_basket(KEY, CONTRACT, 80002, "TOP20-JULY", 60, 1_000_000)
    assert len(sig) == 65
    assert sig[64] in (27, 28)


def test_settle_signature_recovery_matches_signer():
    """Same EIP-712 reconstruction the Solidity SettlementEngine performs."""
    account = Account.from_key(KEY)
    realized, ts, chain = 60, 1234, 80002
    sig = sign_settle_basket(KEY, CONTRACT, chain, "TOP20-JULY", realized, ts)

    recovered = Account.recover_message(
        encode_typed_data(full_message=_settle_typed_data(realized, ts, chain)),
        signature=sig,
    )
    assert recovered.lower() == account.address.lower()


def test_settle_signature_changes_with_every_field():
    sig1 = sign_settle_basket(KEY, CONTRACT, 80002, "TOP20-JULY", 60, 100)
    sig2 = sign_settle_basket(KEY, CONTRACT, 80002, "TOP20-JULY", 60, 101)
    sig3 = sign_settle_basket(KEY, CONTRACT, 80002, "TOP20-JULY", 61, 100)
    sig4 = sign_settle_basket(KEY, CONTRACT, 80002, "TOP20-AUGUST", 60, 100)
    assert len({sig1, sig2, sig3, sig4}) == 4