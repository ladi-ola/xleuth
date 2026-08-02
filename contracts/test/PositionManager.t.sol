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
        pm = new PositionManager(owner, address(vault), address(oracle), MAX_LEVERAGE, STALENESS);

        vm.prank(owner);
        vault.setPositionManager(address(pm));

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
}
