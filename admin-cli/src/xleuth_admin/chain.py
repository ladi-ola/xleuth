"""web3.py chain access for registration (admin/owner key; secret never logged)."""

from __future__ import annotations

import os
import time

SETTLEMENT_ABI = [
    {"inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
     "name": "expiryOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
     "name": "isSettled", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
                {"internalType": "uint256", "name": "expiry", "type": "uint256"}],
     "name": "setBasketExpiry", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
]

ORACLE_ABI = [
    {"inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
     "name": "latestPrice",
     "outputs": [{"internalType": "uint256", "name": "price", "type": "uint256"},
                 {"internalType": "uint256", "name": "timestamp", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]


class RegistrationChain:
    def __init__(self, rpc_url: str, settlement: str, oracle: str, admin_key: str, chain_id: int):
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware
        from eth_account import Account

        if not admin_key.startswith("0x"):
            admin_key = "0x" + admin_key
        self._admin_key = admin_key
        self._admin_addr = Account.from_key(admin_key).address
        self._chain_id = chain_id
        self._w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._settlement = self._w3.eth.contract(address=settlement, abi=SETTLEMENT_ABI)
        self._oracle = self._w3.eth.contract(address=oracle, abi=ORACLE_ABI) if oracle else None

    @staticmethod
    def from_env() -> "RegistrationChain":
        rpc = os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL")
        settlement = os.getenv("SETTLEMENT_ENGINE_ADDRESS")
        oracle = os.getenv("INDEX_ORACLE_CONSUMER_ADDRESS", "")
        key = os.getenv("ADMIN_PRIVATE_KEY") or os.getenv("DEPLOYER_PRIVATE_KEY")
        if not rpc or not settlement or not key:
            raise SystemExit("POLYGON_AMOY_RPC_URL/RPC_URL, SETTLEMENT_ENGINE_ADDRESS and "
                             "ADMIN_PRIVATE_KEY (or DEPLOYER_PRIVATE_KEY) are required")
        return RegistrationChain(rpc, settlement, oracle, key,
                                 int(os.getenv("CHAIN_ID", "80002")))

    @staticmethod
    def _b32(hex_id: str) -> bytes:
        h = hex_id[2:] if hex_id.startswith("0x") else hex_id
        return bytes.fromhex(h)

    def get_expiry(self, index_id_hex: str) -> int:
        return int(self._settlement.functions.expiryOf(self._b32(index_id_hex)).call())

    def is_settled(self, index_id_hex: str) -> bool:
        return bool(self._settlement.functions.isSettled(self._b32(index_id_hex)).call())

    def get_price(self, index_id_hex: str):
        if not self._oracle:
            return None
        p, t = self._oracle.functions.latestPrice(self._b32(index_id_hex)).call()
        return {"price": int(p), "timestamp": int(t)}

    def send_set_expiry(self, index_id_hex: str, expiry: int) -> str:
        nonce = self._w3.eth.get_transaction_count(self._admin_addr, "pending")
        tx = self._settlement.functions.setBasketExpiry(
            self._b32(index_id_hex), int(expiry)).build_transaction({
                "from": self._admin_addr, "nonce": nonce,
                "chainId": self._chain_id, "gas": 200_000,
            })
        signed = self._w3.eth.account.sign_transaction(tx, self._admin_key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def wait_confirmations(self, tx_hash: str, confirmations: int = 2, timeout_s: int = 300) -> bool:
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout_s)
        if receipt.get("status") != 1:
            return False
        if confirmations <= 1:
            return True
        target = receipt["blockNumber"] + confirmations - 1
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if int(self._w3.eth.block_number) >= target:
                return True
            time.sleep(5)
        raise TimeoutError(f"tx {tx_hash} mined but {confirmations} confirmations not reached")
