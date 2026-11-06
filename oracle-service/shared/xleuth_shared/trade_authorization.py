"""V2 execution envelope shared by Python relayers and browser signers.

No key loading or signing happens here. The trader signs EIP-712 in their
existing wallet. The relayer only submits the signed envelope. This module
does NOT opt legacy settlement into the unsafe unilateral PositionManager.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

PRICE_DECIMALS = 3
SIZE_DECIMALS = 6
USDC_DECIMALS = 6
PRICE_SCALE = 10**PRICE_DECIMALS
MAX_PRICE_UNITS = 100 * PRICE_SCALE
MIN_NOTIONAL_UNITS = 10 * 10**USDC_DECIMALS
MAX_NOTIONAL_UNITS = 1_000 * 10**USDC_DECIMALS
UINT256_MAX = 2**256 - 1
ZERO_ID = "0x" + "00" * 32

_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ID = re.compile(r"^0x[0-9a-fA-F]{64}$")

AUTHORIZATION_FIELDS = [
    {"name": "trader", "type": "address"},
    {"name": "basketId", "type": "bytes32"},
    {"name": "orderId", "type": "bytes32"},
    {"name": "side", "type": "uint8"},
    {"name": "size", "type": "uint256"},
    {"name": "maxNotional", "type": "uint256"},
    {"name": "minPrice", "type": "uint256"},
    {"name": "maxPrice", "type": "uint256"},
    {"name": "leverage", "type": "uint256"},
    {"name": "nonce", "type": "uint256"},
    {"name": "deadline", "type": "uint256"},
    {"name": "fillOrKill", "type": "bool"},
    {"name": "reduceOnly", "type": "bool"},
    {"name": "positionId", "type": "bytes32"},
]


def exact_units(value: str | int | Decimal, decimals: int) -> int:
    """Convert human decimal input without binary floats or silent rounding."""
    if isinstance(value, (bool, float)):
        raise ValueError("use a decimal string, not a float")
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 6:
        raise ValueError("unsupported decimal precision")
    if isinstance(value, str) and len(value) > 160:
        raise ValueError("decimal input is too long")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid decimal amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be finite and greater than zero")
    # Bound before scaling so huge exponents cannot become enormous integers.
    if amount > UINT256_MAX:
        raise ValueError("amount exceeds uint256")
    # Decimal's default 28-digit arithmetic context must not round large
    # uint256 values. Work from the exact coefficient/exponent instead.
    sign, digits, exponent = amount.as_tuple()
    if len(digits) > 160:
        raise ValueError("decimal input is too long")
    coefficient = int("".join(map(str, digits)))
    power = exponent + decimals
    if power < 0:
        divisor_power = -power
        if divisor_power > len(digits):
            raise ValueError(f"amount exceeds {decimals}-decimal precision")
        divisor = 10**divisor_power
        if coefficient % divisor:
            raise ValueError(f"amount exceeds {decimals}-decimal precision")
        units = coefficient // divisor
    else:
        if power > 78:
            raise ValueError("amount exceeds uint256")
        units = coefficient * 10**power
    if sign or not 0 < units <= UINT256_MAX:
        raise ValueError("amount exceeds uint256")
    return units


def price_units(value: str | int | Decimal) -> int:
    units = exact_units(value, PRICE_DECIMALS)
    if units > MAX_PRICE_UNITS:
        raise ValueError("price must be at most 100 index points")
    return units


def size_units(value: str | int | Decimal) -> int:
    return exact_units(value, SIZE_DECIMALS)


def notional_units(size: int, price: int, *, round_up: bool = True) -> int:
    """6dp collateral units for 6dp contracts times 3dp index-point price."""
    _uint(size, "size")
    _uint(price, "price")
    value, remainder = divmod(size * price, PRICE_SCALE)
    if round_up and remainder:
        value += 1
    if value > UINT256_MAX:
        raise ValueError("notional exceeds uint256")
    return value


def _uint(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= UINT256_MAX:
        raise ValueError(f"{field} must be a uint256 integer")


@dataclass(frozen=True)
class TradeAuthorization:
    trader: str
    basket_id: str
    order_id: str
    side: int
    size: int
    max_notional: int
    min_price: int
    max_price: int
    leverage: int
    nonce: int
    deadline: int
    fill_or_kill: bool = False
    reduce_only: bool = False
    position_id: str = ZERO_ID

    def __post_init__(self) -> None:
        if not isinstance(self.trader, str) or not _ADDRESS.fullmatch(self.trader):
            raise ValueError("trader must be an EVM address")
        if int(self.trader, 16) == 0:
            raise ValueError("trader cannot be the zero address")
        for field in ("basket_id", "order_id", "position_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError(f"{field} must be bytes32")
        if int(self.basket_id, 16) == 0 or int(self.order_id, 16) == 0:
            raise ValueError("basket_id and order_id cannot be zero")
        for field in ("side", "size", "max_notional", "min_price", "max_price", "leverage", "nonce", "deadline"):
            _uint(getattr(self, field), field)
        if self.side not in (0, 1) or self.size == 0:
            raise ValueError("side/size invalid")
        if not MIN_NOTIONAL_UNITS <= self.max_notional <= MAX_NOTIONAL_UNITS:
            raise ValueError("notional budget must be 10–1000 USDC")
        if not 0 < self.min_price <= self.max_price <= MAX_PRICE_UNITS:
            raise ValueError("price bounds invalid")
        if not 1 <= self.leverage <= 5:
            raise ValueError("leverage must be 1–5")
        if not isinstance(self.fill_or_kill, bool) or not isinstance(self.reduce_only, bool):
            raise ValueError("order flags must be booleans")
        if self.reduce_only and int(self.position_id, 16) == 0:
            raise ValueError("reduce-only authorization requires a position identifier")

    def message(self) -> dict:
        return {
            "trader": self.trader,
            "basketId": self.basket_id,
            "orderId": self.order_id,
            "side": self.side,
            "size": self.size,
            "maxNotional": self.max_notional,
            "minPrice": self.min_price,
            "maxPrice": self.max_price,
            "leverage": self.leverage,
            "nonce": self.nonce,
            "deadline": self.deadline,
            "fillOrKill": self.fill_or_kill,
            "reduceOnly": self.reduce_only,
            "positionId": self.position_id,
        }

    def typed_data(self, chain_id: int, executor_address: str) -> dict:
        _uint(chain_id, "chain_id")
        if chain_id == 0:
            raise ValueError("chain_id must be positive")
        if not isinstance(executor_address, str) or not _ADDRESS.fullmatch(executor_address) or int(executor_address, 16) == 0:
            raise ValueError("executor must be a nonzero EVM address")
        return {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Authorization": [dict(field) for field in AUTHORIZATION_FIELDS],
            },
            "primaryType": "Authorization",
            "domain": {
                "name": "Xleuth Orders",
                "version": "2",
                "chainId": chain_id,
                "verifyingContract": executor_address,
            },
            "message": self.message(),
        }

    def digest(self, chain_id: int, executor_address: str) -> bytes:
        from eth_account.messages import encode_typed_data
        from eth_utils import keccak

        message = encode_typed_data(full_message=self.typed_data(chain_id, executor_address))
        return keccak(b"\x19" + message.version + message.header + message.body)
