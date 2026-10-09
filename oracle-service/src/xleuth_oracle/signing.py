"""EIP-712 signing for IndexOracleConsumer.PriceUpdate messages.

The contract (IndexOracleConsumer.sol) computes:
    digest = _hashTypedDataV4(keccak256(abi.encode(
        keccak256("PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"),
        basketId, price, timestamp)))
domain: EIP712("Xleuth Index Oracle", "1")

and recovers the signer with OpenZeppelin ECDSA against a 65-byte `r||s||v`
signature. This module reproduces that exact digest and signature layout.

The SettlementEngine.SettleBasket message is signed with the same layout,
under domain EIP712("Xleuth Settlement", "1").
"""

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

DOMAIN_NAME = "Xleuth Index Oracle"
DOMAIN_VERSION = "1"

SETTLE_DOMAIN_NAME = "Xleuth Settlement"
SETTLE_DOMAIN_VERSION = "1"

_PRICE_TYPE = "PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"
_SETTLE_TYPE = "SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"


def basket_id_from_name(name: str) -> bytes:
    """BasketId bytes32 = keccak256 of the basket name string, matching the
    contracts' `bytes32 basketA = keccak256("TOP20-JULY")`."""
    return keccak(text=name)


def sign_price_update(
    signer_private_key: str,
    contract_address: str,
    chain_id: int,
    basket_name: str,
    price: int,
    timestamp: int,
    index_id_override: str | bytes | None = None,
) -> bytes:
    """Sign a `PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)` EIP-712
    message and return the raw 65-byte `r||s||v` signature the contract expects."""
    account = Account.from_key(signer_private_key)
    if index_id_override is None:
        basket = basket_id_from_name(basket_name)
    elif isinstance(index_id_override, bytes):
        basket = index_id_override
    else:
        h = index_id_override[2:] if index_id_override.startswith("0x") else index_id_override
        basket = bytes.fromhex(h)

    typed_data = {
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
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": chain_id,
            "verifyingContract": contract_address,
        },
        "message": {
            "basketId": "0x" + basket.hex(),
            "price": int(price),
            "timestamp": int(timestamp),
        },
    }
    signable = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(signable, private_key=signer_private_key)
    # Account.sign_message returns (r, s, v). The contract wants r||s||v (65 bytes).
    sig = signed.signature
    if isinstance(sig, str) and sig.startswith("0x"):
        return bytes.fromhex(sig[2:])
    return bytes(sig)


def sign_settle_basket(
    signer_private_key: str,
    engine_address: str,
    chain_id: int,
    basket_name: str,
    realized_price: int,
    timestamp: int,
    index_id_override: str | bytes | None = None,
) -> bytes:
    """Sign a `SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)`
    EIP-712 message for the SettlementEngine and return the raw 65-byte
    `r||s||v` signature the contract expects."""
    account = Account.from_key(signer_private_key)
    if index_id_override is None:
        basket = basket_id_from_name(basket_name)
    elif isinstance(index_id_override, bytes):
        basket = index_id_override
    else:
        h = index_id_override[2:] if index_id_override.startswith("0x") else index_id_override
        basket = bytes.fromhex(h)

    typed_data = {
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
            "verifyingContract": engine_address,
        },
        "message": {
            "basketId": "0x" + basket.hex(),
            "realizedPrice": int(realized_price),
            "timestamp": int(timestamp),
        },
    }
    signable = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(signable, private_key=signer_private_key)
    sig = signed.signature
    if isinstance(sig, str) and sig.startswith("0x"):
        return bytes.fromhex(sig[2:])
    return bytes(sig)


def price_to_scale(price: float, scale: int = 100) -> int:
    """data-ingestion scaled prices are already 0-100 floats; round half-up and clamp."""
    p = int(price + 0.5) if price >= 0 else int(price - 0.5)
    if p < 1:
        return 1
    if p > scale:
        return scale
    return p