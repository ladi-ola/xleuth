// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";

import {CollateralVault} from "../src/CollateralVault.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {SettlementEngine} from "../src/SettlementEngine.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @notice Expiry settlement tests. Exercises the full stack: a position is
///         opened at an oracle price, the basket reaches its registered expiry,
///         a signed realized YES-fraction value is relayed to the
///         SettlementEngine, and every open position is paid out against it.
///         The realized fraction is written directly here to keep the test
///         hermetic; the off-chain computation over event-deduped live volume
///         lives in the settlement service and is covered by its own tests.
contract SettlementEngineTest is Test {
    uint256 constant CHAIN_ID = 31337;
    uint256 constant PRICE_SCALE = 100;
    uint256 constant MAX_LEVERAGE = 5;
    uint256 constant STALENESS = 60;
    uint256 constant MAINTENANCE_BPS = 125;
    uint256 constant LIQUIDATION_FEE_BPS = 50;
    uint256 constant SETTLE_STALENESS = 3600;
    uint256 constant USD = 1e6;

    address owner = makeAddr("owner");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");
    address stranger = makeAddr("stranger");

    uint256 oracleKey = 0xABCD;
    address oracleSigner = vm.addr(oracleKey);

    uint256 settleKey = 0xBEEF;
    address settleSigner = vm.addr(settleKey);

    bytes32 basketA = keccak256("TOP20-JULY");

    uint256 internal expiry;

    MockUSDC usdc;
    CollateralVault vault;
    IndexOracleConsumer oracle;
    PositionManager pm;
    SettlementEngine engine;

    function setUp() public {
        expiry = 1_000_000;

        usdc = new MockUSDC("Test USDC", "USDC");
        vault = new CollateralVault(address(usdc), owner);
        oracle = new IndexOracleConsumer(owner, oracleSigner, PRICE_SCALE, STALENESS);
        pm = new PositionManager(
            owner,
            address(vault),
            address(oracle),
            MAX_LEVERAGE,
            STALENESS,
            MAINTENANCE_BPS,
            LIQUIDATION_FEE_BPS
        );
        engine = new SettlementEngine(owner, address(pm), settleSigner, PRICE_SCALE, SETTLE_STALENESS);

        vm.prank(owner);
        vault.setPositionManager(address(pm));
        vm.prank(owner);
        pm.setSettlementEngine(address(engine));
        vm.prank(owner);
        engine.setBasketExpiry(basketA, expiry);

        usdc.mint(alice, 100_000 * USD);
        usdc.mint(bob, 100_000 * USD);
        usdc.mint(carol, 100_000 * USD);
    }

    function _deposit(address who, uint256 amount) internal {
        vm.startPrank(who);
        usdc.approve(address(vault), type(uint256).max);
        vault.deposit(amount);
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

    function _signSettle(uint256 realizedPrice, uint256 timestamp)
        internal
        view
        returns (bytes memory)
    {
        bytes32 typeHash =
            keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)");
        bytes32 structHash = keccak256(abi.encode(typeHash, basketA, realizedPrice, timestamp));
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Settlement"),
                keccak256("1"),
                CHAIN_ID,
                address(engine)
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(settleKey, digest);
        return abi.encodePacked(r, s, v);
    }

    /// @dev Opens a 5x long for alice and a 5x short for bob at `price`.
    function _openSpread(address longUser, address shortUser, uint256 price, uint256 size)
        internal
    {
        _deposit(longUser, 100_000 * USD);
        _deposit(shortUser, 100_000 * USD);
        _pushPrice(price, block.timestamp);
        vm.prank(longUser);
        pm.openPosition(basketA, PositionManager.Side.Long, size, 5);
        vm.prank(shortUser);
        pm.openPosition(basketA, PositionManager.Side.Short, size, 5);
    }

    function _printBalances(string memory label, uint256 realized) internal view {
        console.log("=== %s: realized YES fraction = %d / %d index points ===", label, realized, PRICE_SCALE);
        console.log("  alice: free=%d locked=%d", vault.freeBalance(alice), vault.lockedBalance(alice));
        console.log("  bob  : free=%d locked=%d", vault.freeBalance(bob), vault.lockedBalance(bob));
    }

    function _signSettleAltKey(uint256 realizedPrice, uint256 timestamp)
        internal
        view
        returns (bytes memory)
    {
        bytes32 typeHash =
            keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)");
        bytes32 structHash = keccak256(abi.encode(typeHash, basketA, realizedPrice, timestamp));
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Settlement"),
                keccak256("1"),
                CHAIN_ID,
                address(engine)
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xBAD0, digest);
        return abi.encodePacked(r, s, v);
    }

    /// @dev Runs a full settlement: open at `entry`, warp past expiry, settle
    ///      at `realized`.
    ///      PnL for a long = (realized - entry) * size; for a short the mirror.
    function _runSettlement(uint256 entry, uint256 size, uint256 realized, string memory label)
        internal
    {
        uint256 margin = (entry * size) / 5;
        _deposit(alice, 100_000 * USD);
        _deposit(bob, 100_000 * USD);
        _pushPrice(entry, block.timestamp);
        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, size, 5);
        vm.prank(bob);
        pm.openPosition(basketA, PositionManager.Side.Short, size, 5);

        uint256 aliceFreeBefore = vault.freeBalance(alice);
        uint256 bobFreeBefore = vault.freeBalance(bob);
        console.log("[%s] BEFORE settle: alice free=%d locked=%d", label, aliceFreeBefore, vault.lockedBalance(alice));
        console.log("[%s] BEFORE settle: bob   free=%d locked=%d", label, bobFreeBefore, vault.lockedBalance(bob));

        // Warp past expiry FIRST, then sign at the current (fresh) timestamp so
        // the signed message is not stale when relayed.
        vm.warp(expiry);
        bytes memory sig = _signSettle(realized, block.timestamp);
        vm.prank(stranger);
        engine.settleBasket(basketA, realized, block.timestamp, sig);

        console.log("[%s] AFTER  settle: alice free=%d locked=%d", label, vault.freeBalance(alice), vault.lockedBalance(alice));
        console.log("[%s] AFTER  settle: bob   free=%d locked=%d", label, vault.freeBalance(bob), vault.lockedBalance(bob));

        // Long: initial free = 100k*USD - margin. Long PnL = (realized-entry)*size.
        int256 longPnl = (int256(realized) - int256(entry)) * int256(size);
        uint256 longCredit = longPnl >= 0
            ? margin + uint256(longPnl)
            : (int256(margin) + longPnl > 0 ? uint256(int256(margin) + longPnl) : 0);

        int256 shortPnl = (int256(entry) - int256(realized)) * int256(size);
        uint256 shortCredit = shortPnl >= 0
            ? margin + uint256(shortPnl)
            : (int256(margin) + shortPnl > 0 ? uint256(int256(margin) + shortPnl) : 0);

        assertEq(vault.lockedBalance(alice), 0, "alice margin fully released");
        assertEq(vault.lockedBalance(bob), 0, "bob margin fully released");
        assertEq(vault.freeBalance(alice), aliceFreeBefore + longCredit, "alice long settled");
        assertEq(vault.freeBalance(bob), bobFreeBefore + shortCredit, "bob short settled");
    }

    function test_Payout_Realized_30() public {
        // entry 50, size 1000, 5x: margin = 10k. Long PnL = (30-50)*1000 = -20000 -> floor 0.
        // Short PnL = (50-30)*1000 = +20000 -> credit 30000.
        _runSettlement(50, 1_000, 30, "REALIZED-0.30");
        assertEq(vault.freeBalance(alice), 100_000 * USD - 10_000, "long wiped at 0.30");
        assertEq(vault.freeBalance(bob), 100_000 * USD + 20_000, "short +20k net at 0.30");
    }

    function test_Payout_Realized_51() public {
        // entry 50, size 1000, 5x: margin 10k. Long = +1pt*1000 = +1000
        // short = -1000 (keeps 9k of margin). Printed output shows the numbers.
        _runSettlement(50, 1_000, 51, "REALIZED-0.51");
    }

    function test_Payout_Realized_70() public {
        // entry 50, size 1000, 5x: margin 10k. Long wins (70-50)*1000 = +20k
        // -> free 100k*USD + 20k. Short loses -20k on a 10k margin -> wiped,
        // keeps 0 -> free 100k*USD - 10k (margin consumed).
        _runSettlement(50, 1_000, 70, "REALIZED-0.70");
        assertEq(vault.freeBalance(alice), 100_000 * USD + 20_000, "long nets +20k");
        assertEq(vault.freeBalance(bob), 100_000 * USD - 10_000, "short wiped to margin loss");
    }

    function test_Settle_RejectedBeforeExpiry() public {
        _deposit(alice, 100_000 * USD);
        _pushPrice(50, block.timestamp);
        vm.prank(alice);
        pm.openPosition(basketA, PositionManager.Side.Long, 1_000, 5);

        bytes memory sig = _signSettle(60, block.timestamp);
        vm.expectRevert(SettlementEngine.NotExpired.selector);
        engine.settleBasket(basketA, 60, block.timestamp, sig);
    }

    function test_Settle_RejectedForUnknownBasket() public {
        bytes memory sig = _signSettle(60, block.timestamp);
        vm.expectRevert(SettlementEngine.UnknownBasket.selector);
        engine.settleBasket(keccak256("NOT-REGISTERED"), 60, block.timestamp, sig);
    }

    function test_Settle_RejectedForUnauthorizedSigner() public {
        bytes memory sig = _signSettleAltKey(60, block.timestamp);
        vm.warp(expiry);
        vm.expectRevert(SettlementEngine.UnauthorizedSigner.selector);
        engine.settleBasket(basketA, 60, block.timestamp, sig);
    }
}