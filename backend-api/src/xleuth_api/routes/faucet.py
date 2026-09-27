import os
import re
from datetime import datetime, timezone

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, HTTPException, status
from web3 import AsyncWeb3
from web3.exceptions import Web3Exception

from xleuth_api.db import Database
from xleuth_api.dependencies import get_db
from xleuth_shared.schemas.faucet import (
    FaucetClaimRequest,
    FaucetClaimResponse,
    FaucetCooldownResponse,
)

router = APIRouter(prefix="/faucet", tags=["faucet"])

# ERC-20 transfer function signature
ERC20_TRANSFER_SELECTOR = "0xa9059cbb"
# Amount: 10,000 USDC with 6 decimals = 10,000 * 10^6
FAUCET_AMOUNT = 10_000 * 10**6

ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")


def is_valid_address(address: str) -> bool:
    return bool(ADDRESS_REGEX.match(address))


def build_transfer_calldata(to_address: str, amount: int) -> str:
    # ERC-20 transfer(address,uint256)
    # selector (4 bytes) + padded address (32 bytes) + padded amount (32 bytes)
    selector = ERC20_TRANSFER_SELECTOR
    padded_address = to_address[2:].lower().zfill(64)
    padded_amount = hex(amount)[2:].zfill(64)
    return "0x" + selector[2:] + padded_address + padded_amount


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
    db: Database = Depends(get_db),
):
    address = request.smart_account_address.strip()

    if not is_valid_address(address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid EVM address format",
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

    # Get environment variables
    operator_private_key = os.getenv("OPERATOR_PRIVATE_KEY")
    mock_usdc_address = os.getenv("MOCK_USDC_ADDRESS")
    rpc_url = os.getenv("POLYGON_AMOY_RPC_URL")

    if not operator_private_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Operator private key not configured",
        )
    if not mock_usdc_address:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MockUSDC address not configured",
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

        calldata = build_transfer_calldata(address, FAUCET_AMOUNT)

        tx = {
            "to": mock_usdc_address,
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

    return FaucetClaimResponse(tx_hash=tx_hash_hex, status="submitted")