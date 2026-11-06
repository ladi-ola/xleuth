"""Canonical v2 opening intent preimage for SignedOrderExecutor.

The on-chain AtomicTradeLedger decodes five ABI words, and the executor
requires ``order_id == keccak(intent)``. A unique nonzero salt separates
otherwise identical buy and sell orders. This is NOT a transaction signature.
"""

from eth_abi import encode
from eth_utils import keccak

ORDER_KINDS = {"limit": 0, "market": 1, "stop": 2}
_CLOSING_KINDS = {"limit": 0, "market": 1, "stop_loss": 3, "take_profit": 4}


def opening_intent(
    kind: str, *, salt: bytes, trigger_price: int = 0,
) -> tuple[bytes, bytes]:
    """Return (ABI preimage, orderId) for a plain or breakout opening order."""
    if kind not in ORDER_KINDS:
        raise ValueError("only limit, market and breakout stop may open a lot")
    if not isinstance(salt, bytes) or len(salt) != 32 or not any(salt):
        raise ValueError("salt must be nonzero bytes32")
    if isinstance(trigger_price, bool) or not isinstance(trigger_price, int):
        raise ValueError("trigger price must be integer milli-points")
    if kind == "stop":
        if not 0 < trigger_price <= 100_000:
            raise ValueError("breakout stop needs a valid trigger")
    elif trigger_price != 0:
        raise ValueError("only breakout stops may have a trigger")
    intent = encode(
        ["uint8", "uint256", "bytes32", "bytes32", "bytes32"],
        [ORDER_KINDS[kind], trigger_price, b"\x00" * 32, b"\x00" * 32, salt],
    )
    return intent, keccak(intent)


def closing_intent(
    kind: str, *, salt: bytes, position_id: bytes,
    trigger_price: int = 0, oco_group: bytes = b"\x00" * 32,
) -> tuple[bytes, bytes]:
    """A matched lot replacement; the trader must sign reduceOnly=True.

    For bracket orders, ``position_id`` refers to lot index + 1 (bytes32)
    within the signed basket and ``oco_group`` is nonzero. A second attached
    close against the same lot fails after the first transfers ownership.
    """
    if kind not in _CLOSING_KINDS:
        raise ValueError("unsupported close type")
    if not isinstance(salt, bytes) or len(salt) != 32 or not any(salt):
        raise ValueError("salt must be nonzero bytes32")
    if not isinstance(position_id, bytes) or len(position_id) != 32 or not any(position_id):
        raise ValueError("position_id must be nonzero bytes32")
    if not isinstance(oco_group, bytes) or len(oco_group) != 32:
        raise ValueError("oco_group must be bytes32")
    if isinstance(trigger_price, bool) or not isinstance(trigger_price, int):
        raise ValueError("trigger price must be integer milli-points")
    if kind in ("stop_loss", "take_profit"):
        if not 0 < trigger_price <= 100_000 or not any(oco_group):
            raise ValueError("bracket close requires trigger and OCO group")
    elif trigger_price != 0 or any(oco_group):
        raise ValueError("ordinary close cannot specify trigger or OCO group")
    intent = encode(
        ["uint8", "uint256", "bytes32", "bytes32", "bytes32"],
        [_CLOSING_KINDS[kind], trigger_price, oco_group, position_id, salt],
    )
    return intent, keccak(intent)
