// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

contract PositionManagerTest is Test {
    CollateralVault vault;
    IndexOracleConsumer oracle;
    PositionManager pm;
    MockUSDC usdc;

    uint256 constant CHAIN_ID = 31337;
    uint256 constant PRICE_SCALE = 100;
    uint256 constant MAX_LEVERAGE = 5;
    uint256 constant STALENESS = 60;

    address owner = makeAddr("owner");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    uint256 oracleKey = 0xABCD;
    address oracleSigner = vm.addr(oracleKey);

    uint256 constant USD = 1e6;

    bytes32 basketA = keccak256("TOP20-JULY");

    function setUp() public {
        usdc = new MockUSDC("Test USDC", "USDC");
        vault = new CollateralVault(address(usdc), owner);
        oracle = new IndexOracleConsumer(owner, oracleSigner, PRICE_SCALE, STALENESS);
        pm = new PositionManager(
            owner, address(vault), address(oracle), MAX_LEVERAGE, STALENESS, 125, 50
        );

        vm.prank(owner);
        vault.setPositionManager(address(pm));
        // PositionManager now requires an explicit immutable basket expiry.
        // This contract acts as the synthetic settlement engine in legacy
        // behavior tests; production registration goes via SettlementEngine.
        vm.prank(owner);
        pm.setSettlementEngine(address(this));
        pm.registerBasketExpiry(basketA, 1_000_000_000);

        usdc.mint(alice, 100_000 * USD);
        vm.startPrank(alice);
        usdc.approve(address(vault), type(uint256).max);
        vault.deposit(100_000 * USD);
        vm.stopPrank();
    }

    function _pushPrice(uint256 price, uint256 timestamp) internal {
        bytes32 typeHash =
            keccak256("PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)");
        bytes32 structHash = keccak256(abi.encode(typeHash, basketA, price, timestamp));
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Index Oracle"),
                keccak256("1"),
                CHAIN_ID,
                address(oracle)
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oracleKey, digest);
        oracle.pushPrice(basketA, price, timestamp, abi.encodePacked(r, s, v));
    }

    // ── Opening positions ──────────────────────────────────────────────────

    function test_OpenLong_LocksExactMargin() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        // notional = 50 * 1000 = 50,000; margin = /5 = 10,000
        uint256 expectedMargin = (50 * 1_000) / 5;

        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);

        assertEq(vault.freeBalance(alice), 100_000 * USD - expectedMargin);
        assertEq(vault.lockedBalance(alice), expectedMargin);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(uint256(pos.side), uint256(PositionManager.Side.Long));
        assertEq(pos.size, 1_000);
        assertEq(pos.entryPrice, 50);
        assertEq(pos.leverage, 5);
        assertEq(pos.lockedMargin, expectedMargin);
    }

    function test_OpenShort_LocksExactMargin() public {
        vm.warp(1_000);
        _pushPrice(80, 1_000);
        uint256 expectedMargin = (80 * 2_000) / 4;

        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Short, 2_000, 4);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(uint256(pos.side), uint256(PositionManager.Side.Short));
        assertEq(pos.lockedMargin, expectedMargin);
    }

    function testFuzz_OpenLong_MarginIsNotionalOverLeverage(
        uint8 price,
        uint128 size,
        uint8 leverage
    ) public {
        vm.assume(price > 0 && price <= PRICE_SCALE);
        vm.assume(size > 0 && size <= 100_000);
        vm.assume(leverage >= 1 && leverage <= MAX_LEVERAGE);
        vm.assume((uint256(price) * size) / leverage > 0);
        vm.assume((uint256(price) * size) / leverage <= 50_000 * USD);

        vm.warp(1_000);
        _pushPrice(price, 1_000);

        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, size, leverage);

        uint256 expectedMargin = (uint256(price) * size) / leverage;
        assertEq(vault.lockedBalance(alice), expectedMargin);
        assertEq(vault.freeBalance(alice), 100_000 * USD - expectedMargin);
        assertEq(usdc.balanceOf(address(vault)), 100_000 * USD, "tokens stay in vault");
    }

    function test_OpenUndercollateralized_Reverts() public {
        vm.warp(1_000);
        _pushPrice(90, 1_000);
        // notional = 90 * 3e9 = 270e9; margin at 2x = 135e9 > 100e9 free -> revert
        vm.prank(alice);
        vm.expectRevert(CollateralVault.InsufficientFreeBalance.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 3_000_000_000, 2);
    }

    function test_OpenPosition_ExactFreeBalance_Allowed() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        // notional = 50 * 10,000 = 500,000; margin at 5x = 100,000 == bob's full deposit
        usdc.mint(bob, 100_000);
        vm.startPrank(bob);
        usdc.approve(address(vault), type(uint256).max);
        vault.deposit(100_000);
        vm.stopPrank();

        vm.prank(bob);
        pm.openPosition(basketA, PositionManager.Side.Long, 10_000, 5);
        assertEq(vault.freeBalance(bob), 0);
        assertEq(vault.lockedBalance(bob), 100_000);
    }

    function test_OpenPosition_LeverageAboveCap_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.InvalidLeverage.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 6);
    }

    function test_OpenPosition_ZeroLeverage_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.InvalidLeverage.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 0);
    }

    function test_OpenPosition_ZeroSize_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.ZeroSize.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 0, 5);
    }

    function test_OpenPosition_SecondPositionOnSameBasket_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);

        vm.prank(alice);
        vm.expectRevert(PositionManager.PositionExists.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);

        vm.prank(alice);
        vm.expectRevert(PositionManager.PositionExists.selector);
        pm.openPosition(basketA, PositionManager.Side.Short, 1_000, 5);
    }

    function test_OpenPosition_StaleOraclePrice_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);

        vm.warp(1_000 + STALENESS + 1);
        vm.prank(alice);
        vm.expectRevert(PositionManager.PriceNotFresh.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);
    }

    function test_OpenPosition_NoOraclePrice_Reverts() public {
        vm.warp(1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.PriceNotFresh.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);
    }

    // ── Closing positions ──────────────────────────────────────────────────

    function test_ClosePosition_ReleasesMarginToFree() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);
        uint256 margin = (50 * 1_000) / 5;

        vm.warp(2_000);
        vm.prank(alice);
        pm.closePosition(basketA);

        assertEq(vault.freeBalance(alice), 100_000 * USD);
        assertEq(vault.lockedBalance(alice), 0);
        assertEq(usdc.balanceOf(address(vault)), 100_000 * USD, "tokens stay in vault");

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 0);
    }

    function test_ClosePosition_NoPosition_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(PositionManager.NoOpenPosition.selector);
        pm.closePosition(basketA);
    }

    function testFuzz_OpenClose_RoundTrip(uint8 price, uint128 size, uint8 leverage) public {
        vm.assume(price > 0 && price <= PRICE_SCALE);
        vm.assume(size > 0 && size <= 100_000);
        vm.assume(leverage >= 1 && leverage <= MAX_LEVERAGE);
        vm.assume((uint256(price) * size) / leverage > 0);
        vm.assume((uint256(price) * size) / leverage <= 50_000 * USD);

        vm.warp(1_000);
        _pushPrice(price, 1_000);

        vm.startPrank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, size, leverage);
        pm.closePosition(basketA);
        vm.stopPrank();

        assertEq(vault.freeBalance(alice), 100_000 * USD, "free balance restored");
        assertEq(vault.lockedBalance(alice), 0);
        assertEq(usdc.balanceOf(address(vault)), 100_000 * USD, "vault balance unchanged");
        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 0);
    }

    // ── Access control / parameters ────────────────────────────────────────

    function test_SetMaxLeverage_RaisesCap() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);

        vm.prank(owner);
        pm.setMaxLeverage(10);

        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 10);
        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.leverage, 10);
    }

    function test_SetMaxLeverage_LowersCap() public {
        vm.prank(owner);
        pm.setMaxLeverage(2);

        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.InvalidLeverage.selector);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 3);
    }

    function test_SetMaxLeverage_Zero_Reverts() public {
        vm.prank(owner);
        vm.expectRevert(PositionManager.InvalidLeverage.selector);
        pm.setMaxLeverage(0);
    }

    function test_SetMaxLeverage_OnlyOwner() public {
        vm.prank(bob);
        vm.expectRevert();
        pm.setMaxLeverage(10);
    }

    function test_SetMaxStaleness_OnlyOwner() public {
        vm.prank(bob);
        vm.expectRevert();
        pm.setMaxStaleness(120);
    }

    function test_SetMaxStaleness_ExtendsTradeWindow() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);

        vm.prank(owner);
        pm.setMaxStaleness(120);

        vm.warp(1_000 + 90);
        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);
    }

    // ── Liquidation ──────────────────────────────────────────────────────
    // PositionManager constructed with maintenanceMarginRatioBps=125,
    // liquidationFeeBps=50. liquidate() triggers when a position's margin ratio
    //   equity * 1e4 / notional  <  maintenanceMarginRatioBps  (exact: == NOT liquidated).
    // At open leverage L the ratio is exactly 10000/L bps regardless of price,
    // so with L=5 the open ratio is 2000 bps (20%).

    function _openLongAt(address who, uint256 price, uint256 size, uint256 lev) internal {
        _pushPrice(price, 1_000);
        vm.prank(who);
        pm.openPosition(basketA, PositionManager.Side.Long, size, lev);
    }

    function test_Liquidate_PaysLiquidatorAndRemovesPosition() public {
        vm.prank(owner);
        pm.setMaintenanceMarginRatio(2_000);

        // Open at 50, 5x, size 1000 -> margin 10k, notional 50k, ratio 2000 == 2000
        // not liquidatable at the boundary; drop price to 41 to run it under.
        _openLongAt(alice, 50, 1_000, 5);
        assertEq(pm.getPosition(alice, basketA).lockedMargin, 10_000, "margin 10k");
        assertEq(
            pm.equityOf(alice, basketA) * 1e4, 50 * 1_000 * 2_000,
            "open ratio == 2000 bps"
        );
        assertEq(pm.getOpenUserCount(basketA), 1);

        // Price 41: pnl = (41-50)*1000 = -9000, equity = 10 000 - 9 000 = 1 000,
        // ratio = 1000*1e4/41000 = 243.9 < 2000 -> liquidatable.
        vm.warp(2_000);
        _pushPrice(41, 2_000);

        uint256 notional = 41 * 1_000;
        uint256 reward = (notional * 50) / 1e4; // 41000*50/1e4 = 205

        vm.prank(bob);
        pm.liquidate(alice, basketA);

        // reward 205 < equity 1000 -> bob paid 205, alice keeps 795.
        assertEq(vault.lockedBalance(alice), 0, "margin consumed");
        assertEq(vault.freeBalance(bob), reward, "bob earned liquidator reward");
        assertEq(
            vault.freeBalance(alice),
            100_000 * USD - 10_000 + 1_000 - reward,
            "alice keeps equity minus fee"
        );
        assertEq(pm.getPosition(alice, basketA).size, 0, "position closed");
        assertEq(pm.getOpenUserCount(basketA), 0, "removed from open list");
    }

    function test_Liquidate_BelowThreshold_NotLiquidatable() public {
        // Default maintenance 125 bps. Open at 50 5x -> ratio 2000 >= 125, safe.
        _openLongAt(alice, 50, 1_000, 5);
        vm.warp(2_000);
        _pushPrice(50, 2_000);
        vm.prank(bob);
        vm.expectRevert(PositionManager.NotLiquidatable.selector);
        pm.liquidate(alice, basketA);

        // Even after a small drop the ratio stays above 125.
        vm.warp(3_000);
        _pushPrice(49, 3_000);
        vm.prank(bob);
        vm.expectRevert(PositionManager.NotLiquidatable.selector);
        pm.liquidate(alice, basketA);
    }

    // Exact boundary: ratio exactly equal to threshold must NOT liquidate;
    // one unit lower MUST. At 5x leverage the open ratio is 2000 bps, so we set
    // maintenance 2000 bps -> boundary sits at the entry price.
    function test_Liquidate_Boundary_ExactThresholdNotLiquidatable() public {
        vm.prank(owner);
        pm.setMaintenanceMarginRatio(2_000);

        _openLongAt(alice, 50, 1_000, 5);
        assertEq(
            pm.equityOf(alice, basketA) * 1e4,
            50 * 1_000 * 2_000,
            "ratio == threshold exactly"
        );

        vm.warp(2_000);
        _pushPrice(50, 2_000);
        vm.prank(bob);
        vm.expectRevert(PositionManager.NotLiquidatable.selector);
        pm.liquidate(alice, basketA);
    }

    function test_Liquidate_Boundary_OneUnitBelowTriggers() public {
        vm.prank(owner);
        pm.setMaintenanceMarginRatio(2_000);

        _openLongAt(alice, 50, 1_000, 5);

        // Price 49: equity = 10k + (49-50)*1000 = 9k, notional = 49k
        // ratio = 9000*1e4/49000 = 1836.7 bps < 2000 -> liquidatable.
        vm.warp(2_000);
        _pushPrice(49, 2_000);
        vm.prank(bob);
        pm.liquidate(alice, basketA);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 0, "liquidated one unit below the boundary");
    }

    function test_Liquidate_WipedOut_NoReward() public {
        vm.prank(owner);
        pm.setMaintenanceMarginRatio(2_000);

        _openLongAt(alice, 50, 1_000, 5);

        // Price 40: pnl = (40-50)*1000 = -10k, equity = 0 -> liquidator fee
        // capped at 0, no reward paid out.
        vm.warp(2_000);
        _pushPrice(40, 2_000);
        vm.prank(bob);
        pm.liquidate(alice, basketA);

        assertEq(vault.freeBalance(bob), 0, "equity wiped -> no liquidator reward");
        assertEq(
            vault.freeBalance(alice),
            100_000 * USD - 10_000,
            "alice keeps nothing from wiped position"
        );
    }

    // ── updatePosition (Week 5: open / increase / flatten) ────────────────

    function _updateAt(address who, PositionManager.Side side, uint256 size, uint256 lev)
        internal
    {
        vm.prank(who);
        pm.updatePosition(basketA, side, size, lev);
    }

    function test_UpdatePosition_NoPosition_OpensNew() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(uint256(pos.side), uint256(PositionManager.Side.Long));
        assertEq(pos.size, 1_000);
        assertEq(pos.entryPrice, 50);
        assertEq(pos.leverage, 5);
        assertEq(pos.lockedMargin, 10_000);
        assertEq(vault.freeBalance(alice), 100_000 * USD - 10_000);
        assertEq(pm.getOpenUserCount(basketA), 1);
    }

    function test_UpdatePosition_SameSide_IncreasesAndReaverages() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        vm.warp(2_000);
        _pushPrice(60, 2_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        // entry = (50*1000 + 60*1000)/2000 = 55; margin += 60*1000/5 = 12,000.
        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 2_000);
        assertEq(pos.entryPrice, 55);
        assertEq(pos.lockedMargin, 22_000);
        assertEq(vault.freeBalance(alice), 100_000 * USD - 22_000);
        assertEq(pm.getOpenUserCount(basketA), 1, "still one open user");
    }

    function test_UpdatePosition_SameSide_DifferentLeverage_Weighted() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        vm.warp(2_000);
        _pushPrice(50, 2_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 2);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 2_000);
        assertEq(pos.leverage, 3, "(5*1000 + 2*1000)/2000");
        assertEq(pos.lockedMargin, 10_000 + 25_000);
    }

    function test_UpdatePosition_OppositeSide_PartialClose_CreditsPnl() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        // Price 60: closed portion 400 -> pnl (60-50)*400 = 4,000; proportional
        // margin released 10,000*400/1000 = 4,000 -> credit 8,000 to free.
        vm.warp(2_000);
        _pushPrice(60, 2_000);
        _updateAt(alice, PositionManager.Side.Short, 400, 5);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 600, "400 of 1000 closed");
        assertEq(pos.entryPrice, 50, "entry unchanged for remaining");
        assertEq(pos.lockedMargin, 6_000, "remaining 600/1000 of margin");
        assertEq(vault.freeBalance(alice), 100_000 * USD - 10_000 + 8_000);
    }

    function test_UpdatePosition_OppositeSide_PartialClose_LossFloorsAtZero() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        // Price 40: closed portion 400 -> pnl (40-50)*400 = -4,000 vs 4,000
        // proportional margin released -> net credit floored at 0.
        vm.warp(2_000);
        _pushPrice(40, 2_000);
        _updateAt(alice, PositionManager.Side.Short, 400, 5);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 600);
        assertEq(pos.lockedMargin, 6_000);
        assertEq(vault.freeBalance(alice), 100_000 * USD - 10_000, "zero net credit");
    }

    function test_UpdatePosition_OppositeSide_FullClose_RemovesPosition() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        vm.warp(2_000);
        _pushPrice(60, 2_000);
        _updateAt(alice, PositionManager.Side.Short, 1_000, 5);

        // pnl (60-50)*1000 = 10,000; credited 10,000 + 10,000 = 20,000.
        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 0, "fully closed");
        assertEq(vault.freeBalance(alice), 100_000 * USD - 10_000 + 20_000);
        assertEq(pm.getOpenUserCount(basketA), 0);
    }

    function test_UpdatePosition_OppositeSide_Larger_FlipsRemainder() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        // Sell 1500: closes all 1000 (credits 10k margin + 10k pnl), then opens
        // SHORT 500 @60 5x -> margin 60*500/5 = 6,000.
        vm.warp(2_000);
        _pushPrice(60, 2_000);
        _updateAt(alice, PositionManager.Side.Short, 1_500, 5);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(uint256(pos.side), uint256(PositionManager.Side.Short));
        assertEq(pos.size, 500);
        assertEq(pos.entryPrice, 60);
        assertEq(pos.lockedMargin, 6_000);
        assertEq(vault.freeBalance(alice), 100_000 * USD - 10_000 + 20_000 - 6_000);
        assertEq(pm.getOpenUserCount(basketA), 1, "one net position remains");
    }

    function test_UpdatePosition_Short_IncreaseAndFlatten() public {
        vm.warp(1_000);
        _pushPrice(80, 1_000);
        _updateAt(alice, PositionManager.Side.Short, 2_000, 4);

        vm.warp(2_000);
        _pushPrice(80, 2_000);
        _updateAt(alice, PositionManager.Side.Short, 500, 4);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 2_500);
        assertEq(pos.lockedMargin, 40_000 + 10_000);

        vm.warp(3_000);
        _pushPrice(70, 3_000);
        _updateAt(alice, PositionManager.Side.Long, 2_500, 4);
        // short pnl (80-70)*2500 = 25,000 -> credited 50,000 + 25,000.
        assertEq(pm.getPosition(alice, basketA).size, 0);
        assertEq(vault.freeBalance(alice), 100_000 * USD - 50_000 + 75_000);
    }

    function test_UpdatePosition_ZeroSize_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.ZeroSize.selector);
        pm.updatePosition(basketA, PositionManager.Side.Long, 0, 5);
    }

    function test_UpdatePosition_LeverageAboveCap_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.prank(alice);
        vm.expectRevert(PositionManager.InvalidLeverage.selector);
        pm.updatePosition(basketA, PositionManager.Side.Long, 1_000, 6);
    }

    function test_UpdatePosition_StaleOraclePrice_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        vm.warp(1_000 + STALENESS + 1);
        vm.prank(alice);
        vm.expectRevert(PositionManager.PriceNotFresh.selector);
        pm.updatePosition(basketA, PositionManager.Side.Long, 1_000, 5);
    }

    function test_UpdatePosition_Increase_Undercollateralized_Reverts() public {
        vm.warp(1_000);
        _pushPrice(50, 1_000);
        _updateAt(alice, PositionManager.Side.Long, 1_000, 5);

        vm.warp(2_000);
        _pushPrice(90, 2_000);
        vm.prank(alice);
        // 90*3e9/2 = 135e9 >> ~1e11 free balance -> vault reverts, and the
        // existing position must be untouched.
        vm.expectRevert(CollateralVault.InsufficientFreeBalance.selector);
        pm.updatePosition(basketA, PositionManager.Side.Long, 3_000_000_000, 2);

        PositionManager.Position memory pos = pm.getPosition(alice, basketA);
        assertEq(pos.size, 1_000);
        assertEq(pos.lockedMargin, 10_000);
    }

    function testFuzz_UpdatePosition_FullClose_RoundTrip(uint8 price, uint128 size, uint8 leverage)
        public
    {
        vm.assume(price > 0 && price <= PRICE_SCALE);
        vm.assume(size > 0 && size <= 100_000);
        vm.assume(leverage >= 1 && leverage <= MAX_LEVERAGE);
        vm.assume((uint256(price) * size) / leverage > 0);
        vm.assume((uint256(price) * size) / leverage <= 50_000 * USD);

        vm.warp(1_000);
        _pushPrice(price, 1_000);
        _updateAt(alice, PositionManager.Side.Long, size, leverage);

        // Close the full position against the same price: deposit restored.
        vm.warp(2_000);
        _pushPrice(price, 2_000);
        _updateAt(alice, PositionManager.Side.Short, size, leverage);

        assertEq(pm.getPosition(alice, basketA).size, 0);
        assertEq(vault.freeBalance(alice), 100_000 * USD, "deposit fully restored");
        assertEq(vault.lockedBalance(alice), 0);
        assertEq(usdc.balanceOf(address(vault)), 100_000 * USD, "vault token balance conserved");
        assertEq(pm.getOpenUserCount(basketA), 0);
    }
}
