// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

contract CollateralVaultTest is Test {
    CollateralVault vault;
    MockUSDC usdc;

    address owner = makeAddr("owner");
    address pm = makeAddr("positionManager");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    uint256 constant USD = 1e6;

    function setUp() public {
        usdc = new MockUSDC("Test USDC", "USDC");
        vault = new CollateralVault(address(usdc), owner);
        vm.startPrank(owner);
        vault.setPositionManager(pm);
        vm.stopPrank();

        usdc.mint(alice, 100_000 * USD);
        usdc.mint(bob, 100_000 * USD);
    }

    // ── Deposit / withdraw accounting ──────────────────────────────────────

    function test_Deposit_IncreasesFreeBalanceAndVaultBalance() public {
        vm.prank(alice);
        usdc.approve(address(vault), 10_000 * USD);

        vm.prank(alice);
        vault.deposit(10_000 * USD);

        assertEq(vault.freeBalance(alice), 10_000 * USD);
        assertEq(vault.lockedBalance(alice), 0);
        assertEq(usdc.balanceOf(address(vault)), 10_000 * USD);
        assertEq(vault.totalCollateral(), 10_000 * USD);
    }

    function test_Withdraw_DecreasesFreeBalanceAndReturnsTokens() public {
        vm.startPrank(alice);
        usdc.approve(address(vault), type(uint256).max);
        vault.deposit(10_000 * USD);
        vm.stopPrank();

        vm.prank(alice);
        vault.withdraw(4_000 * USD);

        assertEq(vault.freeBalance(alice), 6_000 * USD);
        assertEq(usdc.balanceOf(alice), 100_000 * USD - 10_000 * USD + 4_000 * USD);
        assertEq(usdc.balanceOf(address(vault)), 6_000 * USD);
    }

    function test_Withdraw_MoreThanFree_Reverts() public {
        vm.prank(alice);
        usdc.approve(address(vault), type(uint256).max);
        vm.prank(alice);
        vault.deposit(1_000 * USD);

        vm.prank(alice);
        vm.expectRevert(CollateralVault.InsufficientFreeBalance.selector);
        vault.withdraw(1_000 * USD + 1);
    }

    function test_Withdraw_ZeroAmount_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(CollateralVault.InvalidAmount.selector);
        vault.withdraw(0);
    }

    function test_DepositZero_Reverts() public {
        vm.prank(alice);
        vm.expectRevert(CollateralVault.InvalidAmount.selector);
        vault.deposit(0);
    }

    function testFuzz_Accounting_RoundTrip(uint128 amount) public {
        vm.assume(amount > 0 && amount <= 50_000 * USD);
        uint256 vaultBalanceBefore = usdc.balanceOf(address(vault));
        uint256 aliceWalletBefore = usdc.balanceOf(alice);

        vm.startPrank(alice);
        usdc.approve(address(vault), amount);
        vault.deposit(amount);
        vault.withdraw(amount);
        vm.stopPrank();

        assertEq(usdc.balanceOf(address(vault)), vaultBalanceBefore, "vault balance unchanged");
        assertEq(aliceWalletBefore, usdc.balanceOf(alice), "wallet balance unchanged");
        assertEq(vault.freeBalance(alice), 0, "no free balance residue");
    }

    function testFuzz_MultiUser_DepositsAreIsolated(uint128 amountAlice, uint128 amountBob) public {
        vm.assume(amountAlice > 0 && amountAlice <= 50_000 * USD);
        vm.assume(amountBob > 0 && amountBob <= 50_000 * USD);

        vm.startPrank(alice);
        usdc.approve(address(vault), amountAlice);
        vault.deposit(amountAlice);
        vm.stopPrank();

        vm.startPrank(bob);
        usdc.approve(address(vault), amountBob);
        vault.deposit(amountBob);
        vm.stopPrank();

        assertEq(vault.freeBalance(alice), amountAlice);
        assertEq(vault.freeBalance(bob), amountBob);
        assertEq(vault.totalCollateral(), amountAlice + amountBob);

        vm.prank(alice);
        vault.withdraw(amountAlice);
        assertEq(vault.freeBalance(bob), amountBob, "bob unaffected by alice withdrawal");
        assertEq(usdc.balanceOf(address(vault)), amountBob);
    }

    // ── Margin lock / release ──────────────────────────────────────────────

    function test_LockMargin_MovesFreeToLocked() public {
        vm.startPrank(alice);
        usdc.approve(address(vault), 10_000 * USD);
        vault.deposit(10_000 * USD);
        vm.stopPrank();

        vm.prank(pm);
        vault.lockMargin(alice, 2_500 * USD);

        assertEq(vault.freeBalance(alice), 7_500 * USD);
        assertEq(vault.lockedBalance(alice), 2_500 * USD);
    }

    function test_ReleaseMargin_MovesLockedToFree() public {
        vm.startPrank(alice);
        usdc.approve(address(vault), 10_000 * USD);
        vault.deposit(10_000 * USD);
        vm.stopPrank();

        vm.prank(pm);
        vault.lockMargin(alice, 2_500 * USD);
        vm.prank(pm);
        vault.releaseMargin(alice, 2_500 * USD);

        assertEq(vault.freeBalance(alice), 10_000 * USD);
        assertEq(vault.lockedBalance(alice), 0);
        assertEq(usdc.balanceOf(address(vault)), 10_000 * USD, "tokens never leave vault");
    }

    function test_LockMargin_MoreThanFree_Reverts() public {
        vm.prank(alice);
        usdc.approve(address(vault), 1_000 * USD);
        vm.prank(alice);
        vault.deposit(1_000 * USD);

        vm.prank(pm);
        vm.expectRevert(CollateralVault.InsufficientFreeBalance.selector);
        vault.lockMargin(alice, 1_000 * USD + 1);
    }

    function test_ReleaseMargin_MoreThanLocked_Reverts() public {
        vm.prank(pm);
        vm.expectRevert(CollateralVault.InsufficientLockedBalance.selector);
        vault.releaseMargin(alice, 1);
    }

    function test_LockMargin_OnlyPositionManager() public {
        vm.prank(alice);
        usdc.approve(address(vault), 1_000 * USD);
        vm.prank(alice);
        vault.deposit(1_000 * USD);

        vm.prank(bob);
        vm.expectRevert(CollateralVault.NotPositionManager.selector);
        vault.lockMargin(alice, 1);

        vm.prank(alice);
        vm.expectRevert(CollateralVault.NotPositionManager.selector);
        vault.lockMargin(alice, 1);
    }

    function test_ReleaseMargin_OnlyPositionManager() public {
        vm.prank(bob);
        vm.expectRevert(CollateralVault.NotPositionManager.selector);
        vault.releaseMargin(alice, 1);
    }

    function test_LockedCollateral_CannotBeWithdrawn() public {
        vm.startPrank(alice);
        usdc.approve(address(vault), 10_000 * USD);
        vault.deposit(10_000 * USD);
        vm.stopPrank();

        vm.prank(pm);
        vault.lockMargin(alice, 5_000 * USD);

        vm.prank(alice);
        vm.expectRevert(CollateralVault.InsufficientFreeBalance.selector);
        vault.withdraw(8_000 * USD);
    }

    // ── Settlement / liquidation position closing ──────────────────────────

    function _openWithMargin(address who, uint256 deposit) internal {
        vm.startPrank(who);
        usdc.approve(address(vault), type(uint256).max);
        vault.deposit(deposit);
        vm.stopPrank();
        vm.prank(pm);
        vault.lockMargin(who, deposit / 2);
    }

    function test_SettlePosition_ProfitCreditsFree() public {
        _openWithMargin(alice, 10_000 * USD);
        uint256 lockedBefore = vault.lockedBalance(alice);
        uint256 freeBefore = vault.freeBalance(alice);

        vm.prank(pm);
        vault.settlePosition(alice, lockedBefore, 1_000);

        assertEq(vault.lockedBalance(alice), 0);
        assertEq(vault.freeBalance(alice), freeBefore + lockedBefore + 1_000);
        assertEq(usdc.balanceOf(address(vault)), 10_000 * USD, "tokens stay in vault");
    }

    function test_settlePosition_Loss_ConsumesMarginToZero() public {
        _openWithMargin(alice, 10_000 * USD);
        uint256 locked = vault.lockedBalance(alice);

        vm.prank(pm);
        vault.settlePosition(alice, locked, -int256(locked));

        assertEq(vault.lockedBalance(alice), 0);
        assertEq(vault.freeBalance(alice), 5_000 * USD, "credit floored at zero");
    }

    function test_settlePosition_LossBeyondMargin_FloorsAtZero() public {
        _openWithMargin(alice, 10_000 * USD);
        uint256 locked = vault.lockedBalance(alice);
        uint256 freeBefore = vault.freeBalance(alice);

        // pnl = -2 * locked -> total is negative; user is NOT pushed negative.
        vm.prank(pm);
        vault.settlePosition(alice, locked, -int256(locked) * 2);

        assertEq(vault.lockedBalance(alice), 0);
        assertEq(vault.freeBalance(alice), freeBefore, "free balance untouched (floored at 0)");
        assertEq(vault.balanceOf(alice), freeBefore);
    }

    function test_settlePosition_NonPositionManager_Reverts() public {
        vm.prank(bob);
        vm.expectRevert(CollateralVault.NotPositionManager.selector);
        vault.settlePosition(alice, 1, 0);
    }

    function test_LiquidatePosition_PaysLiquidatorAndReturnsEquity() public {
        _openWithMargin(alice, 10_000 * USD);
        uint256 locked = vault.lockedBalance(alice); // 5_000 USD
        uint256 reward = 500 * USD;
        int256 pnl = 0;

        vm.prank(pm);
        vault.liquidatePosition(alice, bob, locked, pnl, reward);

        // equity = locked + 0 = 5_000 USD; bob gets 500, alice gets 4_500.
        assertEq(vault.lockedBalance(alice), 0);
        assertEq(vault.freeBalance(bob), reward);
        assertEq(vault.freeBalance(alice), 5_000 * USD + (5_000 * USD - reward));
        assertEq(usdc.balanceOf(address(vault)), 10_000 * USD, "tokens stay in vault");
    }

    function test_liquidatePosition_NegativeEquity_NoRefundToUser() public {
        _openWithMargin(alice, 10_000 * USD);
        uint256 locked = vault.lockedBalance(alice); // 5_000 USD
        vm.prank(pm);
        // pnl = -6_000, equity = -1_000: nothing for user, nothing for liquidator.
        vault.liquidatePosition(alice, bob, locked, -6_000 * int256(USD), 100 * USD);

        assertEq(vault.lockedBalance(alice), 0);
        assertEq(vault.freeBalance(bob), 0, "no equity so no liquidator reward");
        assertEq(vault.freeBalance(alice), 5_000 * USD, "user keeps original free only");
    }

    function test_liquidatePosition_RewardCappedByEquity() public {
        _openWithMargin(alice, 10_000 * USD);
        uint256 locked = vault.lockedBalance(alice);
        // Reward larger than equity: payout floored at equity.
        vm.prank(pm);
        vault.liquidatePosition(alice, bob, locked, 0, locked + 1_000 * USD);

        assertEq(vault.freeBalance(bob), locked, "reward capped at equity");
        assertEq(vault.freeBalance(alice), 5_000 * USD, "nothing left beyond capped reward");
    }

    function test_LiquidatePosition_OnlyPositionManager() public {
        vm.prank(bob);
        vm.expectRevert(CollateralVault.NotPositionManager.selector);
        vault.liquidatePosition(alice, bob, 1, 0, 0);
    }

    // ── Access control ─────────────────────────────────────────────────────

    function test_SetPositionManager_OnlyOwner() public {
        vm.prank(bob);
        vm.expectRevert();
        vault.setPositionManager(bob);
    }

    function test_SetPositionManager_AllowsNewOperator() public {
        vm.startPrank(owner);
        vault.setPositionManager(bob);
        vm.stopPrank();

        vm.startPrank(alice);
        usdc.approve(address(vault), 1_000 * USD);
        vault.deposit(1_000 * USD);
        vm.stopPrank();

        vm.prank(bob);
        vault.lockMargin(alice, 500 * USD);
        assertEq(vault.lockedBalance(alice), 500 * USD);
    }
}
