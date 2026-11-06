import os
from datetime import datetime, timezone
from functools import partial

import pytest

from xleuth_oracle.config import OracleConfig


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("POLYGON_AMOY_RPC_URL", raising=False)
    monkeypatch.delenv("RPC_URL", raising=False)
    monkeypatch.delenv("INDEX_ORACLE_CONSUMER_ADDRESS", raising=False)
    monkeypatch.delenv("ORACLE_SIGNER_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("DEPLOYER_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("CHAIN_ID", raising=False)
    monkeypatch.delenv("ACTIVE_BASKETS", raising=False)


def test_config_requires_rpc(monkeypatch):
    monkeypatch.setenv("INDEX_ORACLE_CONSUMER_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("ORACLE_SIGNER_PRIVATE_KEY", "0x" + "12" * 32)
    with pytest.raises(ValueError, match="RPC"):
        OracleConfig.load()


def test_config_requires_contract(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://localhost:8545")
    monkeypatch.setenv("ORACLE_SIGNER_PRIVATE_KEY", "0x" + "12" * 32)
    with pytest.raises(ValueError, match="INDEX_ORACLE_CONSUMER_ADDRESS"):
        OracleConfig.load()


def test_config_requires_key(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://localhost:8545")
    monkeypatch.setenv("INDEX_ORACLE_CONSUMER_ADDRESS", "0x" + "11" * 20)
    with pytest.raises(ValueError, match="ORACLE_SIGNER_PRIVATE_KEY"):
        OracleConfig.load()


def test_config_defaults(monkeypatch):
    from xleuth_oracle import config
    from xleuth_shared.basket_lifecycle import active_basket_names

    monkeypatch.setattr(config, "active_basket_names", partial(
        active_basket_names, now=datetime(2026, 10, 18, tzinfo=timezone.utc)))
    monkeypatch.setenv("RPC_URL", "http://localhost:8545")
    monkeypatch.setenv("INDEX_ORACLE_CONSUMER_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("ORACLE_SIGNER_PRIVATE_KEY", "0x" + "12" * 32)
    # Pin the example month instead of relying on the test-run date.
    monkeypatch.setenv("ACTIVE_BASKETS", "TOP20-OCTOBER")

    cfg = OracleConfig.load()
    assert cfg.chain_id == 80002
    assert cfg.price_scale == 100
    assert cfg.max_staleness == 60
    assert cfg.push_interval_seconds == 15
    assert cfg.retry_max_attempts == 5
    assert cfg.retry_backoff_seconds == 2
    # TOP20-OCTOBER is a literal dated basket — resolves to itself.
    assert "TOP20-OCTOBER" in cfg.baskets


def test_config_prefers_amoy_rpc(monkeypatch):
    monkeypatch.setenv("POLYGON_AMOY_RPC_URL", "https://amoy.example")
    monkeypatch.setenv("RPC_URL", "http://other")
    monkeypatch.setenv("INDEX_ORACLE_CONSUMER_ADDRESS", "0x" + "11" * 20)
    monkeypatch.setenv("ORACLE_SIGNER_PRIVATE_KEY", "0x" + "12" * 32)
    cfg = OracleConfig.load()
    assert cfg.rpc_url == "https://amoy.example"
