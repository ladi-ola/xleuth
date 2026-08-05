"""On-chain push of signed PriceUpdate messages to IndexOracleConsumer.

Handles RPC failures with retry/backoff (never silently drop a price). A push is
only skipped when we have no price for the basket (logged loudly) or when the
oracle already holds the identical (price, timestamp) — fresh pushes always use
a new timestamp so ordering is preserved.
"""

import asyncio
import logging

from xleuth_oracle.config import OracleConfig
from xleuth_oracle.signing import basket_id_from_name, price_to_scale, sign_price_update

logger = logging.getLogger("xleuth_oracle.pusher")

ORACLE_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            {"internalType": "uint256", "name": "price", "type": "uint256"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "pushPrice",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"}
        ],
        "name": "latestPrice",
        "outputs": [
            {"internalType": "uint256", "name": "price", "type": "uint256"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


class Pusher:
    def __init__(self, config: OracleConfig):
        self.config = config
        self._w3 = None
        self._contract = None

    def connect(self, provider_class=None, provider_kwargs: dict | None = None) -> None:
        from web3 import Web3

        if self._w3 is not None:
            return
        if provider_class is None:
            from web3.middleware import ExtraDataToPOAMiddleware

            self._w3 = Web3(Web3.HTTPProvider(self.config.rpc_url, request_kwargs={"timeout": 20}))
            self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        else:
            klass = provider_class
            kwargs = provider_kwargs or {}
            if "default_account" not in kwargs:
                kwargs["default_account"] = self.config.signer_address
            self._w3 = Web3(klass(**kwargs))

        self._contract = self._w3.eth.contract(
            address=self.config.contract_address, abi=ORACLE_ABI
        )
        logger.info(
            "Pusher connected. signer=%s contract=%s chain_id=%d",
            self.config.signer_address,
            self.config.contract_address,
            self.config.chain_id,
        )

    @property
    def w3(self):
        if self._w3 is None:
            self.connect()
        return self._w3

    @property
    def contract(self):
        if self._contract is None:
            self.connect()
        return self._contract

    def latest_onchain_price(self, basket_name: str) -> tuple[int, int] | None:
        """(price, timestamp) of the last accepted on-chain update, or None."""
        try:
            result = self.contract.functions.latestPrice(
                basket_id_from_name(basket_name)
            ).call()
            return int(result[0]), int(result[1])
        except Exception:
            logger.warning("latestPrice read failed for %s", basket_name, exc_info=True)
            return None

    def current_timestamp(self) -> int:
        return int(self.w3.eth.get_block("latest")["timestamp"])

    def _send(self, basket_name: str, price: int, timestamp: int, nonce: int) -> bytes:
        signature = sign_price_update(
            self.config.signer_private_key,
            self.config.contract_address,
            self.config.chain_id,
            basket_name,
            price,
            timestamp,
        )
        tx = self.contract.functions.pushPrice(
            basket_id_from_name(basket_name), price, timestamp, signature
        ).build_transaction(
            {
                "from": self.config.signer_address,
                "nonce": nonce,
                "gas": 200_000,
                "chainId": self.config.chain_id,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, self.config.signer_private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.get("status") != 1:
            logger.error(
                "Reverted push %s price=%d (receipt status=%s)",
                basket_name, price, receipt.get("status"),
            )
            return False
        logger.info(
            "Pushed %s price=%d ts=%d block=%s tx=%s",
            basket_name, price, timestamp, receipt.get("blockNumber"), tx_hash.hex(),
        )
        return True

    async def push_all(self, prices: dict[str, float | None]) -> None:
        """Sign + push the latest price per basket with retry/backoff."""
        if not prices:
            return
        for basket_name, raw_price in prices.items():
            if raw_price is None:
                logger.warning("No price for basket %s; skipping push this cycle", basket_name)
                continue
            price = price_to_scale(raw_price, self.config.price_scale)
            await self._push_with_retry(basket_name, price)

    async def _push_with_retry(self, basket_name: str, price: int) -> bool:
        for attempt in range(1, self.config.retry_max_attempts + 1):
            try:
                timestamp = self.current_timestamp()
                latest = self.latest_onchain_price(basket_name)
                if latest is not None and latest == (price, timestamp):
                    logger.debug("On-chain %s already at price=%d ts=%d", basket_name, price, timestamp)
                    return True
                nonce = self.w3.eth.get_transaction_count(self.config.signer_address, "pending")
                ok = await asyncio.to_thread(self._send, basket_name, price, timestamp, nonce)
                if ok:
                    return True
            except Exception as exc:
                logger.error(
                    "Push attempt %d/%d for %s failed: %s",
                    attempt, self.config.retry_max_attempts, basket_name, exc,
                )
            backoff = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
            if attempt < self.config.retry_max_attempts:
                logger.info("Backing off %ds before retrying %s ...", backoff, basket_name)
                await asyncio.sleep(backoff)
        logger.error("Gave up after %d attempts on %s", self.config.retry_max_attempts, basket_name)
        return False