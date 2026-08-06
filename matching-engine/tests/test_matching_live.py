"""Live integration test against the Amoy-deployed contracts (Week 5 spec 6).

Places two real opposing limit orders through the engine's HTTP API, shows:
  * the match, with the fill confirmed ONLY after the PositionManager
    updatePosition transaction mined (tx hash in the response),
  * a direct on-chain read afterward proving both traders' positions,
  * a leverage-cap-exceeding order rejected with the code-path reason.

Requires: oracle-service pushing fresh prices (engine rejects stale prices),
Amoy RPC, and trader wallets with test-USDC (the test mints + deposits its
own USDC via the open-mint MockUSDC and the vault).

Run:  PYTHONPATH=matching-engine/src:shared .venv/bin/pytest \
          matching-engine/tests/test_matching_live.py -s
"""

import time

import jwt as pyjwt
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from xleuth_matching.api import create_app
from xleuth_matching.config import MatchingConfig
from xleuth_matching.margin_check import Web3ChainState
from xleuth_matching.settlement import Web3TxSubmitter

load_dotenv()

USDC_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
VAULT_DEPOSIT_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@pytest.fixture(scope="module")
def cfg() -> MatchingConfig:
    return MatchingConfig.load()


@pytest.fixture(scope="module")
def chain(cfg) -> Web3ChainState:
    return Web3ChainState(cfg)


@pytest.fixture(scope="module")
def client(cfg) -> TestClient:
    return TestClient(create_app(cfg))


def _token(cfg: MatchingConfig, wallet: str) -> dict:
    token = pyjwt.encode(
        {"sub": wallet.lower(), "exp": int(time.time()) + 3600},
        cfg.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _ensure_pol(cfg: MatchingConfig, wallet: str, min_pol: float = 0.2) -> None:
    """Top up the trader's POL for gas from DEPLOYER_PRIVATE_KEY if low."""
    import os

    from eth_account import Account
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 20}))
    account = Account.from_key(cfg.trader_keys[wallet.lower()])
    balance = w3.eth.get_balance(account.address)
    if balance >= w3.to_wei(min_pol, "ether"):
        return
    deployer_key = os.getenv("DEPLOYER_PRIVATE_KEY", "")
    if not deployer_key:
        raise RuntimeError("trader needs POL gas; set DEPLOYER_PRIVATE_KEY to fund them")
    deployer = Account.from_key(deployer_key if deployer_key.startswith("0x") else "0x" + deployer_key)
    tip = w3.to_wei(30, "gwei")  # Amoy min tip is 25 gwei
    tx = {
        "from": deployer.address,
        "to": account.address,
        "value": w3.to_wei(1, "ether"),
        "nonce": w3.eth.get_transaction_count(deployer.address, "pending"),
        "gas": 21_000,
        "maxFeePerGas": w3.eth.gas_price + tip,
        "maxPriorityFeePerGas": tip,
        "chainId": cfg.chain_id,
    }
    signed = deployer.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f"  [gas] funded {account.address} 1 POL tx={tx_hash}")


def _fund_trader(cfg: MatchingConfig, wallet: str, amount_usdc: int) -> None:
    """Mint test-USDC, approve the vault, deposit. Idempotent if already funded."""
    import os

    from eth_account import Account
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 20}))
    key = cfg.trader_keys[wallet.lower()]
    account = Account.from_key(key)
    usdc = w3.eth.contract(address=os.getenv("TEST_USDC_ADDRESS"), abi=USDC_ABI)
    vault = w3.eth.contract(address=cfg.vault_address, abi=VAULT_DEPOSIT_ABI)

    base_fee = w3.eth.gas_price
    tip = w3.to_wei(30, "gwei")  # Amoy min tip is 25 gwei
    nonce = w3.eth.get_transaction_count(account.address, "pending")

    def build_and_send(fn, **tx_kwargs):
        nonlocal nonce
        tx = fn.build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": 200_000,
                "maxFeePerGas": base_fee + tip,
                "maxPriorityFeePerGas": tip,
                "chainId": cfg.chain_id,
                **tx_kwargs,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        nonce += 1
        return tx_hash

    tx_hash = build_and_send(usdc.functions.mint(account.address, amount_usdc))
    print(f"  [fund] minted {amount_usdc} USDC -> {account.address} tx={tx_hash}")
    tx_hash = build_and_send(usdc.functions.approve(cfg.vault_address, amount_usdc))
    print(f"  [fund] approved vault tx={tx_hash}")
    tx_hash = build_and_send(vault.functions.deposit(amount_usdc))
    print(f"  [fund] deposited {amount_usdc} USDC tx={tx_hash}")


def _place_with_retry(client, cfg, wallet, body, attempts=6, pause=12):
    """Retry placement while the oracle feed is momentarily stale."""
    last = None
    for _ in range(attempts):
        resp = client.post("/orders", json=body, headers=_token(cfg, wallet))
        if resp.status_code != 422 or "oracle_price_stale" not in resp.json().get("detail", ""):
            return resp
        last = resp
        print(f"  oracle stale, waiting {pause}s for next push...")
        time.sleep(pause)
    return last


def test_live_match_and_onchain_settlement(cfg, chain, client):
    basket = "TOP20-AUGUST"
    wallets = sorted(cfg.trader_keys)
    assert len(wallets) >= 2, "need at least two TRADER*_PRIVATE_KEY wallets"
    alice, bob = wallets[0], wallets[1]

    print(f"\nEngine live test on {cfg.rpc_url} basket={basket}")
    print(f"  traders: alice={alice} bob={bob}")

    for wallet in (alice, bob):
        _ensure_pol(cfg, wallet)
        if chain.free_balance(wallet) < 200_000_000:  # < 200 USDC
            _fund_trader(cfg, wallet, 1_000_000_000)  # deposit 1000 USDC
        print(f"  {wallet} free USDC = {chain.free_balance(wallet) / 1e6}")

    before_a = _position(chain, alice, basket)
    before_b = _position(chain, bob, basket)
    print(f"  positions before: alice={before_a} bob={before_b}")

    size = 20.0
    alice_resp = _place_with_retry(
        client,
        cfg,
        alice,
        {"basket_name": basket, "side": "buy", "price": 30.0, "size": size, "leverage": 5},
    )
    assert alice_resp.status_code == 201, alice_resp.text
    alice_order = alice_resp.json()
    print(f"  alice order {alice_order['order_id']} status={alice_order['status']}")

    bob_resp = client.post(
        "/orders",
        json={"basket_name": basket, "side": "sell", "price": 25.0, "size": size, "leverage": 5},
        headers=_token(cfg, bob),
    )
    assert bob_resp.status_code == 201, bob_resp.text
    bob_order = bob_resp.json()
    print(f"  bob order {bob_order['order_id']} status={bob_order['status']}")

    assert bob_order["status"] == "filled", bob_order
    fills = bob_order["fills"]
    assert len(fills) == 1
    fill = fills[0]
    assert fill["confirmed"] is True, fill
    tx_hash = fill["tx_hash"]
    print(f"\nMATCH at price={fill['price']} size={fill['size']}")
    print(f"FILL CONFIRMED tx_hash={tx_hash}")

    # The fill was only confirmed after the tx mined: verify on-chain.
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"timeout": 20}))
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    assert receipt is not None and receipt["status"] == 1, f"tx {tx_hash} not mined/reverted"

    pos_a = _position(chain, alice, basket)
    pos_b = _position(chain, bob, basket)
    print(f"\nON-CHAIN READS after match:")
    print(f"  alice position = {pos_a} (was {before_a})")
    print(f"  bob   position = {pos_b} (was {before_b})")
    assert _expect_after(before_a, "Long", 20) == pos_a, f"alice position wrong: {pos_a}"
    assert _expect_after(before_b, "Short", 20) == pos_b, f"bob position wrong: {pos_b}"
    print("  PASS: both on-chain positions reflect the match (+20 long / -20 short)")


def _position(chain: Web3ChainState, wallet: str, basket: str) -> tuple[str, int]:
    """(side, size) from PositionManager.getPosition; side 'Long'/'Short'."""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(chain._w3.provider.endpoint_uri, request_kwargs={"timeout": 20}))
    pm = w3.eth.contract(
        address=chain._pm.address,
        abi=[
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
            }
        ],
    )
    side, size, _, _, _ = pm.functions.getPosition(
        Web3.to_checksum_address(wallet), Web3ChainState.basket_id(basket)
    ).call()
    return ("Long" if side == 0 else "Short", int(size))


def _expect_after(before: tuple[str, int], fill_side: str, fill_size: int) -> tuple[str, int]:
    """Position after applying an updatePosition of fill_side/fill_size."""
    side, size = before
    if size == 0:
        return fill_side, fill_size
    if side == fill_side:
        return side, size + fill_size
    # opposite side: flatten first, remainder re-opens on the fill side
    if size > fill_size:
        return side, size - fill_size
    return fill_side, fill_size - size


def test_live_leverage_cap_and_margin_rejection(cfg, client):
    wallet = sorted(cfg.trader_keys)[0]
    print("\nEngine rejection tests")

    resp = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 30.0, "size": 20.0, "leverage": 6},
        headers=_token(cfg, wallet),
    )
    assert resp.status_code == 422
    assert "leverage_out_of_range" in resp.json()["detail"], resp.text
    print(f"  leverage=6 rejected: {resp.json()['detail']}")

    resp = client.post(
        "/orders",
        json={"basket_name": "TOP20-AUGUST", "side": "buy", "price": 30.0, "size": 1_000_000.0, "leverage": 5},
        headers=_token(cfg, wallet),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "insufficient_margin" in detail, resp.text
    print(f"  oversized order rejected: {detail}")
