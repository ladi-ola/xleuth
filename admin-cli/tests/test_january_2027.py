from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from xleuth_admin import selection_runner
from xleuth_shared.baskets import generate_name, make_slug


@pytest.mark.asyncio
async def test_admin_preview_matches_ingestion_window(monkeypatch):
    expiry = datetime(2027, 2, 1, tzinfo=timezone.utc)
    start = datetime(2027, 1, 1, tzinfo=timezone.utc)

    class Client(selection_runner.PolymarketClient):
        def __init__(self):
            pass

        async def get_midpoints_batch(self, tokens):
            return {token: 0.5 for token in tokens}

        async def close(self):
            pass

    async def markets(client):
        return [
            {"conditionId": "old", "endDate": "2026-01-10T00:00:00Z", "volumeNum": 999999},
            {"conditionId": "new", "endDate": "2027-01-10T00:00:00Z", "volumeNum": 100,
             "question": "new", "clobTokenIds": ["yes", "no"]},
            {"conditionId": "february", "endDate": "2027-02-01T00:00:00Z", "volumeNum": 999999},
        ]

    monkeypatch.setattr(selection_runner, "PolymarketClient", Client)
    monkeypatch.setattr(selection_runner, "_fetch_all_markets", markets)
    result = await selection_runner.dry_run_report(
        market_count=20, expiry_at=expiry, window_start=start,
    )
    assert result["actual_count"] == 1
    assert result["constituents"][0]["question"] == "new"
    assert result["ready_for_registration"] is False
    assert result["missing_live_volume_count"] == 1
    assert result["vwap_preview"] is None
    assert result["constituents"][0]["volume"] is None
    assert generate_name("TOP", 20, expiry) == "TOP20-JANUARY"
    assert make_slug("TOP", 20, expiry) == "top20-2027-01"


@pytest.mark.asyncio
async def test_preview_ready_only_with_complete_live_volume_and_valid_prices(monkeypatch):
    class Client(selection_runner.PolymarketClient):
        def __init__(self):
            pass

        async def get_midpoints_batch(self, tokens):
            return {token: 0.50123 for token in tokens}

        async def close(self):
            pass

    monkeypatch.setattr(selection_runner, "PolymarketClient", Client)
    monkeypatch.setattr(selection_runner, "_fetch_all_markets", AsyncMock(return_value=[{
        "conditionId": "new", "endDate": "2027-01-10T00:00:00Z",
        "volumeNum": 999999, "clobTokenIds": ["yes", "no"],
    }]))
    monkeypatch.setattr(selection_runner, "build_volume_map", AsyncMock(return_value={"new": 100.0}))
    result = await selection_runner.dry_run_report(
        market_count=1, expiry_at=datetime(2027, 2, 1, tzinfo=timezone.utc),
        window_start=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    assert result["ready_for_registration"] is True
    assert result["warnings"] == []
    assert result["total_volume"] == 100.0  # Never Gamma's 999999.
    assert result["vwap_scaled_preview"] == 50.123


@pytest.fixture
def registration(monkeypatch):
    from xleuth_admin import cli, chain
    from xleuth_shared import db_baskets

    row = {
        "slug": "top20-2027-01", "market_count": 20, "status": "draft",
        "expiry_at": datetime(2027, 2, 1, tzinfo=timezone.utc),
        "window_start": datetime(2027, 1, 1, tzinfo=timezone.utc),
    }
    pool = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(cli, "_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db_baskets, "get_by_slug", AsyncMock(return_value=row))
    transition = AsyncMock()
    monkeypatch.setattr(db_baskets, "transition", transition)
    from_env = Mock(side_effect=AssertionError("unready preview must not load an owner key"))
    monkeypatch.setattr(chain.RegistrationChain, "from_env", from_env)
    args = SimpleNamespace(slug=row["slug"], force=False, confirmations=2, timeout=300)
    return cli, row, pool, transition, from_env, args


@pytest.mark.asyncio
@pytest.mark.parametrize("report", [
    {"actual_count": 0, "ready_for_registration": False},
    {"actual_count": 19, "ready_for_registration": False, "warnings": ["too few liquid markets"]},
    {"actual_count": 20, "ready_for_registration": False, "warnings": ["missing live volume"]},
    {"actual_count": 20},  # Old/unknown report shape must fail closed.
])
async def test_unready_registration_refuses_before_owner_key_access(monkeypatch, registration, report):
    cli, _, pool, transition, from_env, args = registration
    monkeypatch.setattr(selection_runner, "dry_run_report", AsyncMock(return_value=report))
    assert await cli.cmd_register(args) == 1
    from_env.assert_not_called()
    transition.assert_not_awaited()
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("already_registered", [True, False])
async def test_ready_registration_checks_window_and_requires_confirmation(
    monkeypatch, registration, already_registered,
):
    cli, row, pool, transition, from_env, args = registration
    preview = AsyncMock(return_value={"actual_count": 20, "ready_for_registration": True})
    monkeypatch.setattr(selection_runner, "dry_run_report", preview)
    fake_chain = SimpleNamespace(
        get_expiry=Mock(return_value=int(row["expiry_at"].timestamp()) if already_registered else 0),
        send_set_expiry=Mock(return_value="0xsynthetic-registration"),
        wait_confirmations=Mock(return_value=True),
    )
    from_env.side_effect = None
    from_env.return_value = fake_chain
    assert await cli.cmd_register(args) == 0
    assert preview.call_args.kwargs["window_start"] == row["window_start"]
    assert preview.call_args.kwargs["expiry_at"] == row["expiry_at"]
    assert [call.args[2] for call in transition.await_args_list] == ["registering", "active"]
    if already_registered:
        fake_chain.send_set_expiry.assert_not_called()
    else:
        fake_chain.send_set_expiry.assert_called_once()
        fake_chain.wait_confirmations.assert_called_once_with(
            "0xsynthetic-registration", confirmations=2, timeout_s=300)
    pool.close.assert_awaited_once()
