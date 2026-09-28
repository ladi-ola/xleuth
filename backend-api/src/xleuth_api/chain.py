"""Chain state reading for backend API.

Provides read-only access to on-chain state for portfolio summary, positions, etc.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from web3 import Web3
from eth_utils import keccak

logger = logging.getLogger("xleuth_api.chain")


@dataclass
class ChainConfig:
    rpc_url: str
    vault_address: str
    position_manager_address: str
    oracle_consumer_address: str
    chain_id: int


class ChainStateReader(ABC):
    """Abstract interface for reading chain state."""

    @abstractmethod
    def free_balance(self, wallet: str) -> int:
        """User's free (unlocked) USDC balance in the CollateralVault (6-dp units)."""

    @abstractmethod
    def get_position(self, wallet: str, basket_name: str) -> tuple[int, int, int, int, int] | None:
        """Get full position: (side, size, entry_price, leverage, locked_margin).
        Returns None if no position or error. Side: 0=Long, 1=Short."""

    @abstractmethod
    def oracle_price(self, basket_name: str) -> tuple[int, int] | None:
        """(price_int, timestamp) of latest oracle price, or None."""

    @abstractmethod
    def max_leverage(self) -> int:
        """Current PositionManager.maxLeverage."""


class Web3ChainStateReader(ChainStateReader):
    """web3.py reads against the deployed vault / PositionManager / oracle."""

    ORACLE_ABI = [
        {
            "inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
            "name": "latestPrice",
            "outputs": [
                {"internalType": "uint256", "name": "price", "type": "uint256"},
                {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            ],
            "stateMutability": "view",
            "type": "function",
        }
    ]
    VAULT_ABI = [
        {
            "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
            "name": "freeBalance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]
    PM_ABI = [
        {
            "inputs": [],
            "name": "maxLeverage",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "address", "name": "user", "type": "address"},
                {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            ],
            "name": "getPosition",
            "outputs": [
                {"internalType": "enum PositionManager.Side", "name": "side", "type": "uint8"},
                {"internalType": "uint256", "name": "size", "type": "uint256"},
                {"internalType": "uint256", "name": "entryPrice", "type": "uint256"},
                {"internalType": "uint256", "name": "leverage", "type": "uint256"},
                {"internalType": "uint256", "name": "lockedMargin", "type": "uint256"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
    ]

    def __init__(self, config: ChainConfig):
        self.config = config
        self._w3 = Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 15}))
        self._checksum = Web3.to_checksum_address
        self._oracle = self._w3.eth.contract(
            address=config.oracle_consumer_address, abi=self.ORACLE_ABI
        )
        self._vault = self._w3.eth.contract(address=config.vault_address, abi=self.VAULT_ABI)
        self._pm = self._w3.eth.contract(
            address=config.position_manager_address, abi=self.PM_ABI
        )

    @staticmethod
    def basket_id(basket_name: str) -> bytes:
        return keccak(text=basket_name)

    def free_balance(self, wallet: str) -> int:
        try:
            return int(self._vault.functions.freeBalance(self._checksum(wallet)).call())
        except Exception:
            logger.warning("freeBalance read failed for %s", wallet, exc_info=True)
            return 0

    def get_position(self, wallet: str, basket_name: str) -> tuple[int, int, int, int, int] | None:
        try:
            result = self._pm.functions.getPosition(
                self._checksum(wallet), self.basket_id(basket_name)
            ).call()
            side = int(result[0])
            size = int(result[1])
            entry_price = int(result[2])
            leverage = int(result[3])
            locked_margin = int(result[4])
            if size == 0:
                return None
            return (side, size, entry_price, leverage, locked_margin)
        except Exception:
            logger.warning("getPosition read failed for %s/%s", wallet, basket_name, exc_info=True)
            return None

    def oracle_price(self, basket_name: str) -> tuple[int, int] | None:
        try:
            price, ts = self._oracle.functions.latestPrice(self.basket_id(basket_name)).call()
            return int(price), int(ts)
        except Exception:
            logger.warning("oracle latestPrice read failed for %s", basket_name, exc_info=True)
            return None

    def max_leverage(self) -> int:
        try:
            return int(self._pm.functions.maxLeverage().call())
        except Exception:
            logger.warning("maxLeverage read failed", exc_info=True)
            return 0