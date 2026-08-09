"""Week-6 full end-to-end live test on Polygon Amoy.

The whole system, one chain:

  real Polymarket data  ->  data-ingestion computes the basket VWAP
        ->  oracle-service Pusher signs + pushes it on-chain
        ->  matching engine matches two real orders
        ->  PositionManager opens both positions on-chain
        ->  owner registers the basket's expiry on the SettlementEngine
        ->  a signed SettleBasket message is relayed
        ->  SettlementEngine settles every open position and pays out

Design choices (per Week-6 PLAN):
  * DEDICATED TEST BASKET: the test uses TOP20-MARCH-2027 by default (a
    year-suffixed name stays upcoming/tradeable regardless of the current
    month; real markets exist that far out). Pick a fresh, un-settled month
    via E2E_BASKET_NAME after each run — the live demo baskets
    (TOP20-AUGUST/SEPTEMBER) stay tradeable on the shared Amoy deployment.
    The basket is settled at the end, permanently — expect this test to be
    run once per basket name.
  * The realized settlement value is the basket's freshly computed index
    price (the only honest realized value available pre-expiry), displaced
    by a small signed delta so one side wins and one loses measurably.
  * Every step is narrated with tx hashes and contract reads.

Requires: Amoy RPC, real Polymarket endpoints, oracle key + deployer key +
settlement key + two trader keys in the environment (root .env), and the
Week-5/6 deployed contracts (vault/PM/oracle consumer/SettlementEngine).

Run:
  make test-e2e
or:
  PYTHONPATH=data-ingestion/src:oracle-service/src:matching-engine/src:shared \
    .venv/bin/pytest matching-engine/tests/test_e2e_live.py -v -s
"""

import asyncio
import os
import time
from dataclasses import replace

import jwt as pyjwt
import pytest
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

load_dotenv()

TEST_BASKET = os.getenv("E2E_BASKET_NAME", "TOP20-MARCH-2027")
RPC_URL = os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL")

ENGINE_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
        "name": "isSettled",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
        "name": "expiryOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            {"internalType": "uint256", "name": "expiry", "type": "uint256"},
        ],
        "name": "setBasketExpiry",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            {"internalType": "uint256", "name": "realizedPrice", "type": "uint256"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "settleBasket",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

VAULT_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "freeBalance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "lockedBalance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

PM_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            {"internalType": "enum PositionManager.Side", "name": "side", "type": "uint8"},
            {"internalType": "uint256", "name": "size", "type": "uint256"},
            {"internalType": "uint256", "name": "leverage", "type": "uint256"},
        ],
        "name": "updatePosition",
        "outputs": [],
        "stateMutability": "nonpayable",
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
    {
        "inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
        "name": "getOpenUserCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

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


# ── step helpers ─────────────────────────────────────────────────────────


def _w3() -> Web3:
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 20}))
    from web3.middleware import ExtraDataToPOAMiddleware

    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def _key(env_name: str, fallback: str = "") -> str:
    value = os.getenv(env_name, "") or fallback
    return value if value.startswith("0x") else "0x" + value


def _token(cfg, wallet: str) -> dict:
    token = pyjwt.encode(
        {"sub": wallet.lower(), "exp": int(time.time()) + 3600},
        cfg.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _ensure_pol(cfg, wallet: str, min_pol: float = 0.2) -> None:
    w3 = _w3()
    account = Account.from_key(cfg.trader_keys[wallet.lower()])
    if w3.eth.get_balance(account.address) >= w3.to_wei(min_pol, "ether"):
        return
    deployer_key = os.getenv("DEPLOYER_PRIVATE_KEY", "")
    if not deployer_key:
        raise RuntimeError("trader needs POL gas; set DEPLOYER_PRIVATE_KEY to fund them")
    deployer = Account.from_key(_key("DEPLOYER_PRIVATE_KEY"))
    tip = w3.to_wei(30, "gwei")
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
    print(f"    [gas] funded {account.address} 1 POL tx={tx_hash}")


def _fund_trader(cfg, wallet: str, amount_usdc: int) -> None:
    w3 = _w3()
    account = Account.from_key(cfg.trader_keys[wallet.lower()])
    usdc = w3.eth.contract(address=os.getenv("TEST_USDC_ADDRESS"), abi=USDC_ABI)
    vault = w3.eth.contract(address=cfg.vault_address, abi=VAULT_DEPOSIT_ABI)

    base_fee = w3.eth.gas_price
    tip = w3.to_wei(30, "gwei")
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

    tx = build_and_send(usdc.functions.mint(account.address, amount_usdc))
    print(f"    [fund] minted {amount_usdc} USDC -> {account.address} tx={tx}")
    tx = build_and_send(usdc.functions.approve(cfg.vault_address, amount_usdc))
    print(f"    [fund] approved vault tx={tx}")
    tx = build_and_send(vault.functions.deposit(amount_usdc))
    print(f"    [fund] deposited {amount_usdc} USDC tx={tx}")


def _send_call(w3: Web3, account, fn, gas: int = 300_000) -> str:
    """Build/sign/send a contract call with the Amoy gas tip, return tx hash."""
    base_fee = w3.eth.gas_price
    tip = w3.to_wei(30, "gwei")
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "gas": gas,
            "maxFeePerGas": base_fee + tip,
            "maxPriorityFeePerGas": tip,
            "chainId": int(os.getenv("CHAIN_ID", "80002")),
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    assert receipt["status"] == 1, f"tx {tx_hash} reverted"
    return tx_hash


@pytest.mark.asyncio
async def test_full_e2e_live():
    from fastapi.testclient import TestClient

    from xleuth_ingestion.basket_builder import _fetch_all_markets, build_basket
    from xleuth_ingestion.polymarket_client import PolymarketClient
    from xleuth_matching.api import create_app
    from xleuth_matching.config import MatchingConfig
    from xleuth_matching.margin_check import Web3ChainState
    from xleuth_oracle.config import OracleConfig
    from xleuth_oracle.pusher import Pusher
    from xleuth_oracle.signing import basket_id_from_name, price_to_scale, sign_settle_basket

    cfg = MatchingConfig.load()
    engine_cfg = replace(cfg, baskets=[TEST_BASKET])
    oracle_cfg = OracleConfig.load()

    w3 = _w3()
    engine_addr = os.getenv("SETTLEMENT_ENGINE_ADDRESS")
    assert engine_addr, "SETTLEMENT_ENGINE_ADDRESS required"
    engine = w3.eth.contract(address=engine_addr, abi=ENGINE_ABI)
    vault = w3.eth.contract(address=cfg.vault_address, abi=VAULT_ABI)
    pm = w3.eth.contract(address=cfg.position_manager_address, abi=PM_ABI)
    basket_id = basket_id_from_name(TEST_BASKET)

    if engine.functions.isSettled(basket_id).call():
        pytest.skip(f"basket {TEST_BASKET} already settled; pick a fresh E2E_BASKET_NAME")

    wallets = sorted(engine_cfg.trader_keys)
    assert len(wallets) >= 2, "need at least two TRADER*_PRIVATE_KEY wallets"
    alice, bob = wallets[0], wallets[1]

    print(f"\n{'=' * 70}\nFULL E2E on {RPC_URL}  basket={TEST_BASKET}")
    print(f"  alice={alice}  bob={bob}")
    print(f"  contracts: vault={cfg.vault_address} pm={cfg.position_manager_address} "
          f"oracle={cfg.oracle_consumer_address} engine={engine_addr}")

    # ── STEP 1: real Polymarket data -> data-ingestion basket VWAP ────────
    print("\nSTEP 1 — real Polymarket data -> data-ingestion basket VWAP")
    client = PolymarketClient(
        gamma_api_base=os.getenv("POLYMARKET_GAMMA_API_BASE"),
        clob_api_base=os.getenv("POLYMARKET_CLOB_API_BASE"),
        data_api_base=os.getenv("POLYMARKET_DATA_API_BASE"),
    )
    try:
        all_markets = await _fetch_all_markets(client)
        result = await build_basket(
            TEST_BASKET,
            client=client,
            exclude_categories=os.getenv("EXCLUDE_CATEGORIES", "sports"),
            markets=all_markets,
        )
    finally:
        await client.close()

    assert result["index_price"] is not None, (
        f"basket {TEST_BASKET} produced no index price (no liquid December markets?)"
    )
    scaled = result["index_price_scaled"]
    print(f"  fetched {len(all_markets)} markets; {result['total_constituents']} "
          f"constituents in basket (excluded {result['markets_filtered_out']})")
    print(f"  INDEX VWAP = {result['index_price']:.4f} (scaled {scaled})")
    assert 0 < scaled <= 100

    # ── STEP 2: oracle-service pushes the VWAP on-chain ───────────────────
    print("\nSTEP 2 — oracle-service Pusher signs + pushes the price on-chain")
    pusher = Pusher(oracle_cfg)
    await pusher.push_all({TEST_BASKET: float(scaled)})
    price_onchain, ts_onchain = w3.eth.contract(
        address=cfg.oracle_consumer_address,
        abi=Web3ChainState.ORACLE_ABI,
    ).functions.latestPrice(basket_id).call()
    print(f"  on-chain latestPrice({TEST_BASKET}) = {price_onchain} @ ts={ts_onchain}")
    assert price_onchain == price_to_scale(float(scaled)), "on-chain price != computed VWAP"

    # ── STEP 3: fund traders, then match a real order ─────────────────────
    print("\nSTEP 3 — fund traders; place two opposing orders")
    for wallet in (alice, bob):
        _ensure_pol(engine_cfg, wallet)

    _flatten_leftovers(w3, engine_cfg, pm, basket_id, wallets)

    for wallet in (alice, bob):
        if w3.eth.contract(
            address=cfg.vault_address, abi=VAULT_ABI
        ).functions.freeBalance(Web3.to_checksum_address(wallet)).call() < 400_000_000:
            _fund_trader(engine_cfg, wallet, 1_000_000_000)  # 1000 USDC
        print(f"  {wallet} free USDC = {_free(vault, wallet) / 1e6}")

    app = create_app(engine_cfg)
    test_client = TestClient(app)

    size = 20.0
    alice_resp = _place_with_retry(
        test_client,
        engine_cfg,
        alice,
        {"basket_name": TEST_BASKET, "side": "buy", "price": 30.0, "size": size, "leverage": 5},
    )
    assert alice_resp.status_code == 201, alice_resp.text
    alice_order = alice_resp.json()
    print(f"  alice order {alice_order['order_id']} status={alice_order['status']}")

    bob_resp = test_client.post(
        "/orders",
        json={"basket_name": TEST_BASKET, "side": "sell", "price": 25.0, "size": size, "leverage": 5},
        headers=_token(engine_cfg, bob),
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
    print(f"\n  MATCH at price={fill['price']} size={fill['size']}")
    print(f"  FILL CONFIRMED (updatePosition mined) tx_hash={tx_hash}")

    # ── STEP 4: verify both positions opened on-chain ─────────────────────
    print("\nSTEP 4 — on-chain reads of the opened positions")
    pos_a = _position(pm, alice, basket_id)
    pos_b = _position(pm, bob, basket_id)
    print(f"  alice: {pos_a}")
    print(f"  bob:   {pos_b}")
    assert pos_a[0] == "Long" and pos_a[1] == 20, pos_a
    assert pos_b[0] == "Short" and pos_b[1] == 20, pos_b
    entry_price = pos_a[2]
    assert entry_price == price_onchain, "entry price != pushed oracle price"
    assert pm.functions.getOpenUserCount(basket_id).call() == 2

    free_before_alice = _free(vault, alice)
    free_before_bob = _free(vault, bob)
    locked_before_alice = _locked(vault, alice)
    locked_before_bob = _locked(vault, bob)

    # ── STEP 5: register the basket's expiry (owner) ──────────────────────
    print("\nSTEP 5 — register basket expiry on the SettlementEngine (owner)")
    owner = Account.from_key(_key("DEPLOYER_PRIVATE_KEY"))
    expiry = w3.eth.get_block("latest")["timestamp"]
    tx = _send_call(w3, owner, engine.functions.setBasketExpiry(basket_id, expiry))
    onchain_expiry = engine.functions.expiryOf(basket_id).call()
    print(f"  expiry registered for {TEST_BASKET}: {onchain_expiry} tx={tx}")
    assert onchain_expiry == expiry

    # ── STEP 6: settle at a realized value (signed, any relayer) ──────────
    # The realized value displaces the fresh index price by a small delta so
    # one side demonstrably wins and the other loses.
    settle_key = _key("SETTLEMENT_SIGNER_PRIVATE_KEY", os.getenv("DEPLOYER_PRIVATE_KEY", ""))
    delta = max(1, entry_price // 5 - 1)
    if entry_price + delta <= 100:
        realized = entry_price + delta
    else:
        realized = entry_price - delta
    assert 1 <= realized <= 100

    print(f"\nSTEP 6 — settle {TEST_BASKET} at realized={realized} (entry={entry_price}, "
          f"delta={delta:+d})")
    settle_ts = w3.eth.get_block("latest")["timestamp"]
    sig = sign_settle_basket(
        settle_key, engine_addr, int(os.getenv("CHAIN_ID", "80002")),
        TEST_BASKET, realized, settle_ts,
    )
    relayer = Account.from_key(_key("DEPLOYER_PRIVATE_KEY"))
    tx = _send_call(
        w3, relayer, engine.functions.settleBasket(basket_id, realized, settle_ts, sig), gas=1_000_000
    )
    print(f"  settleBasket relayed tx={tx}")
    assert engine.functions.isSettled(basket_id).call() is True

    # ── STEP 7: verify payouts ────────────────────────────────────────────
    print("\nSTEP 7 — payout verification")
    print(f"  positions after settle: alice={_position(pm, alice, basket_id)} "
          f"bob={_position(pm, bob, basket_id)}")
    assert pm.functions.getOpenUserCount(basket_id).call() == 0
    assert _position(pm, alice, basket_id)[1] == 0
    assert _position(pm, bob, basket_id)[1] == 0

    margin = (entry_price * 20) // 5
    pnl_long = (realized - entry_price) * 20
    pnl_short = -pnl_long

    free_after_alice = _free(vault, alice)
    free_after_bob = _free(vault, bob)
    delta_alice = free_after_alice - free_before_alice
    delta_bob = free_after_bob - free_before_bob
    print(f"  margin each = {margin} USDC, pnl long={pnl_long:+d}, pnl short={pnl_short:+d}")
    print(f"  alice free: {free_before_alice} -> {free_after_alice} (delta {delta_alice:+d})")
    print(f"  bob   free: {free_before_bob} -> {free_after_bob} (delta {delta_bob:+d})")
    print(f"  locked: alice {locked_before_alice} -> {_locked(vault, alice)} "
          f"bob {locked_before_bob} -> {_locked(vault, bob)}")

    # free balance was debited `margin` at open, then credited
    # `margin + pnl` at settle (free_before is read post-debit), so each
    # side's net delta is `max(0, margin + pnl)`: the solvent side gets its
    # margin back plus its full pnl, while a wiped side simply never gets
    # its (already debited) margin back.
    expected_alice = max(0, margin + pnl_long)
    expected_bob = max(0, margin + pnl_short)
    assert delta_alice == expected_alice, (delta_alice, expected_alice)
    assert delta_bob == expected_bob, (delta_bob, expected_bob)

    # The test-basket margin was fully released on settle. Note: these wallets
    # may hold OTHER live positions (e.g. the shared demo basket), so verify
    # the locked delta rather than an absolute zero.
    assert _locked(vault, alice) == locked_before_alice - margin, (
        _locked(vault, alice), locked_before_alice, margin
    )
    assert _locked(vault, bob) == locked_before_bob - margin, (
        _locked(vault, bob), locked_before_bob, margin
    )

    print(f"\n{'=' * 70}\nE2E PASS: real data -> VWAP -> on-chain oracle -> matched orders "
          f"-> positions -> expiry -> paid out.")
    print(f"  fill tx: {tx_hash}")
    print(f"  settle tx: {tx}")
    print(f"  entry={entry_price} realized={realized} | alice pnl={pnl_long:+d} "
          f"bob pnl={pnl_short:+d}")


# ── helpers ───────────────────────────────────────────────────────────────


def _free(vault, wallet: str) -> int:
    return int(vault.functions.freeBalance(Web3.to_checksum_address(wallet)).call())


def _locked(vault, wallet: str) -> int:
    return int(vault.functions.lockedBalance(Web3.to_checksum_address(wallet)).call())


def _position(pm, wallet: str, basket_id: bytes) -> tuple[str, int, int]:
    side, size, entry, _, _ = pm.functions.getPosition(
        Web3.to_checksum_address(wallet), basket_id
    ).call()
    return ("Long" if side == 0 else "Short", int(size), int(entry))


def _flatten_leftovers(w3: Web3, cfg, pm, basket_id: bytes, wallets: list[str]) -> None:
    """Idempotency guard: flatten any open position left by a previous
    partial run so the test always starts from a clean slate. A fresh oracle
    price must already be on-chain (STEP 2) for flatten's freshness check."""
    cleaned = False
    for wallet in wallets:
        side, size, _, leverage, _ = pm.functions.getPosition(
            Web3.to_checksum_address(wallet), basket_id
        ).call()
        if int(size) == 0:
            continue
        account = Account.from_key(cfg.trader_keys[wallet.lower()])
        flat_side = 1 - int(side)
        print(f"  [reset] leftover position {wallet}: flattening "
              f"side={flat_side} size={size} lev={leverage}")
        tx = _send_call(
            w3, account, pm.functions.updatePosition(basket_id, flat_side, int(size), int(leverage))
        )
        print(f"  [reset] flattened tx={tx}")
        cleaned = True
    if not cleaned:
        print("  [reset] no leftover positions")


def _place_with_retry(client, cfg, wallet, body, attempts=6, pause=12):
    """Retry placement while the oracle feed is momentarily stale."""
    last = None
    for _ in range(attempts):
        resp = client.post("/orders", json=body, headers=_token(cfg, wallet))
        if resp.status_code != 422 or "oracle_price_stale" not in resp.json().get("detail", ""):
            return resp
        last = resp
        print(f"    oracle stale, waiting {pause}s for next push...")
        time.sleep(pause)
    return last
