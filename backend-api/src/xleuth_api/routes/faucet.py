import os
import re
from datetime import datetime, timezone

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, HTTPException, status
from web3 import AsyncWeb3
from web3.exceptions import Web3Exception

from xleuth_api.db import Database
from xleuth_api.dependencies import get_current_user, get_db
from xleuth_shared.schemas.faucet import (
    FaucetClaimRequest,
    FaucetClaimResponse,
    FaucetCooldownResponse,
)

router = APIRouter(prefix="/faucet", tags=["faucet"])

# ERC-20 function signatures
ERC20_TRANSFER_SELECTOR = "0xa9059cbb"
ERC20_BALANCE_OF_SELECTOR = "0x70a08231"
ERC20_MINT_SELECTOR = "0x40c10f19"
# Amount: 1,000 USDC with 6 decimals = 1,000 * 10^6 (max 1,000 per 24h claim)
FAUCET_AMOUNT = 1_000 * 10**6
# How long to wait for the funding transaction to be mined. A short wait lets
# the client's immediate balance refetch see the claim; the portfolio also
# polls, so a timeout is not fatal.
RECEIPT_TIMEOUT_SECONDS = 90

ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")


def is_valid_address(address: str) -> bool:
    return bool(ADDRESS_REGEX.match(address))


def _encode_call(selector: str, args: list) -> str:
    # ABI-encode a function call:
    # selector (4 bytes) + each 32-byte, left-padded argument.
    encoded = selector[2:]
    for arg in args:
        encoded += hex(arg)[2:].zfill(64)
    return "0x" + encoded


def build_transfer_calldata(to_address: str, amount: int) -> str:
    # ERC-20 transfer(address,uint256)
    return _encode_call(ERC20_TRANSFER_SELECTOR, [int(to_address, 16), amount])


def build_mint_calldata(to_address: str, amount: int) -> str:
    # ERC-20 mint(address,uint256) — the test-USDC faucet token exposes an
    # open (testnet-only) mint, so the operator can fund itself or a user even
    # when its reserve is empty.
    return _encode_call(ERC20_MINT_SELECTOR, [int(to_address, 16), amount])


def build_balance_of_calldata(holder: str) -> str:
    return _encode_call(ERC20_BALANCE_OF_SELECTOR, [int(holder, 16)])


@router.post(
    "/claim",
    response_model=FaucetClaimResponse,
    responses={
        400: {"description": "Invalid address format"},
        429: {"model": FaucetCooldownResponse, "description": "Cooldown active"},
        500: {"description": "Blockchain transaction failed"},
    },
)
async def claim_faucet(
    request: FaucetClaimRequest,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    # Authenticated claims only: no token -> 401 token_missing (login-gated).
    address = request.smart_account_address.strip()

    if not is_valid_address(address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid EVM address format",
        )

    # The recipient must be the caller's own wallet: anyone authenticated
    # must not be able to direct test funds to an arbitrary address.
    if address.lower() != user["wallet_address"].lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Claim recipient must match the authenticated wallet",
        )

    # Check cooldown (24 hours = 86400 seconds)
    last_claim = await db.get_last_faucet_claim(address)
    if last_claim:
        now = datetime.now(timezone.utc)
        elapsed = (now - last_claim).total_seconds()
        if elapsed < 86400:
            retry_after = int(86400 - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Faucet claim on cooldown",
                headers={"Retry-After": str(retry_after)},
            )

    # Get environment variables. The faucet must fund the vault's collateral
    # token (TEST_USDC_ADDRESS); MOCK_USDC_ADDRESS is only a fallback for
    # deployments that mint a separate faucet token.
    operator_private_key = os.getenv("OPERATOR_PRIVATE_KEY")
    token_address = os.getenv("TEST_USDC_ADDRESS") or os.getenv("MOCK_USDC_ADDRESS")
    rpc_url = os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL")

    if not operator_private_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Operator private key not configured",
        )
    if not token_address:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Test-USDC address not configured",
        )
    if not rpc_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RPC URL not configured",
        )

    # Build transaction
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
    operator_account = Account.from_key(operator_private_key)

    try:
        nonce = await w3.eth.get_transaction_count(operator_account.address)
        gas_price = await w3.eth.gas_price

        # Prefer transferring from the operator's reserve; fall back to the
        # testnet faucet token's open mint when the reserve is short so claims
        # keep working (and still land in the same asset the vault custodies).
        operator_reserve = 0
        try:
            raw_balance = await w3.eth.call(
                {
                    "to": token_address,
                    "data": build_balance_of_calldata(operator_account.address),
                }
            )
            operator_reserve = int.from_bytes(raw_balance, "big")
        except Exception:
            # A token without balanceOf is unusable; let the send surface it.
            operator_reserve = 0

        if operator_reserve >= FAUCET_AMOUNT:
            calldata = build_transfer_calldata(address, FAUCET_AMOUNT)
        else:
            calldata = build_mint_calldata(address, FAUCET_AMOUNT)

        tx = {
            "to": token_address,
            "data": calldata,
            "value": 0,
            "nonce": nonce,
            "chainId": 80002,  # Polygon Amoy
            "gas": 100_000,
            "gasPrice": gas_price,
        }

        # Estimate gas
        try:
            estimated_gas = await w3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated_gas * 1.2)  # 20% buffer
        except Exception:
            pass  # Use default gas if estimation fails

        # Sign and send
        signed_tx = operator_account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = tx_hash.hex()

    except Web3Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction failed: {str(e)}",
        )

    # Record claim in database
    await db.record_faucet_claim(address)

    # Wait briefly for the transfer to be mined so the client's immediate
    # balance refetch reflects the claim. If it is still pending, the
    # portfolio polling picks it up later.
    tx_status = "submitted"
    try:
        receipt = await w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS
        )
        if receipt.get("status") == 1:
            tx_status = "confirmed"
    except Exception:
        # Timeout or receipt lookup failure: leave it as submitted.
        pass

    return FaucetClaimResponse(tx_hash=tx_hash_hex, status=tx_status)