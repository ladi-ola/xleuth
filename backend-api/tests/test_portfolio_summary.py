"""Portfolio summary + faucet funding tests.

The faucet delivers test-USDC to the user's wallet. Only the vault's free
balance is tradeable margin, so the summary reports the two balances
separately: wallet funds are visible but do not count as free margin until
they are deposited. These tests cover that with a fake chain reader, and pin
the faucet's ABI encoders to the token the vault actually custodies.
"""

from fastapi.testclient import TestClient

from xleuth_api.chain import ChainStateReader
from xleuth_api.routes.faucet import (
    build_balance_of_calldata,
    build_mint_calldata,
    build_transfer_calldata,
)

ALICE = "0x" + "a" * 40


def _internal_token(client: TestClient, dynamic_token: str = "valid-dynamic-token") -> str:
    resp = client.post("/auth/verify", json={"token": dynamic_token})
    assert resp.status_code == 200, f"Verify failed: {resp.text}"
    return resp.json()["access_token"]


class FakeChain(ChainStateReader):
    def __init__(self, free: float = 0.0, wallet: float = 0.0):
        self._free = int(free * 1e6)
        self._wallet = int(wallet * 1e6)

    def free_balance(self, wallet: str) -> int:
        return self._free

    def wallet_balance(self, wallet: str) -> int:
        return self._wallet

    def get_position(self, wallet: str, basket_name: str):
        return None

    def oracle_price(self, basket_name: str):
        return None

    def max_leverage(self) -> int:
        return 5


def test_summary_shows_wallet_collateral_but_not_as_margin(client: TestClient, app):
    """A faucet claim is visible in the total, but not tradeable until deposited."""
    app.state.chain_reader = FakeChain(free=0.0, wallet=1000.0)
    token = _internal_token(client)
    resp = client.get("/accounts/summary", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_balance"] == 1000.0
    assert body["free_margin"] == 0.0
    assert body["vault_free"] == 0.0
    assert body["wallet_balance"] == 1000.0
    assert body["used_margin"] == 0.0


def test_summary_sums_wallet_and_vault_for_total_only(client: TestClient, app):
    app.state.chain_reader = FakeChain(free=250.0, wallet=1000.0)
    token = _internal_token(client)
    body = client.get(
        "/accounts/summary", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert body["total_balance"] == 1250.0
    assert body["free_margin"] == 250.0
    assert body["vault_free"] == 250.0
    assert body["wallet_balance"] == 1000.0


def test_summary_tolerates_reader_without_wallet_balance(client: TestClient, app):
    """Older/duck-typed readers that only expose free_balance must still work."""

    class LegacyReader:
        def free_balance(self, wallet: str) -> int:
            return int(500 * 1e6)

    app.state.chain_reader = LegacyReader()
    token = _internal_token(client)
    body = client.get(
        "/accounts/summary", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert body["total_balance"] == 500.0
    assert body["free_margin"] == 500.0
    assert body["vault_free"] == 500.0
    assert body["wallet_balance"] == 0.0


def test_wallet_balance_defaults_to_zero():
    """Readers that cannot resolve the collateral token must not break."""

    class MinimalChain(ChainStateReader):
        def free_balance(self, wallet: str) -> int:
            return 0

        def get_position(self, wallet: str, basket_name: str):
            return None

        def oracle_price(self, basket_name: str):
            return None

        def max_leverage(self) -> int:
            return 0

    assert MinimalChain().wallet_balance(ALICE) == 0


def test_faucet_calldata_matches_collateral_token_abi():
    # transfer(address,uint256)
    assert (
        build_transfer_calldata(ALICE, 1_000 * 10**6)
        == "0xa9059cbb"
        + "0" * 24
        + "a" * 40
        + hex(1_000 * 10**6)[2:].zfill(64)
    )
    # mint(address,uint256) — used when the operator reserve is short.
    assert build_mint_calldata(ALICE, 1_000 * 10**6).startswith("0x40c10f19")
    # balanceOf(address)
    assert build_balance_of_calldata(ALICE).startswith("0x70a08231")
