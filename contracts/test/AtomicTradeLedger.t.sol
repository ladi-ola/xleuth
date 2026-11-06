// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {AtomicTradeLedger} from "../src/AtomicTradeLedger.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {MockUSDC} from "../src/MockUSDC.sol";
import {IAtomicTradeLedger, SignedOrderExecutor} from "../src/SignedOrderExecutor.sol";

contract AtomicTradeLedgerTest is Test {
    MockUSDC token;
    IndexOracleConsumer oracle;
    AtomicTradeLedger ledger;
    SignedOrderExecutor executor;
    uint256 constant KEY = 0xC0FFEE;
    bytes32 constant BASKET = keccak256("top20-2027-04");
    address buyer = makeAddr("buyer");
    address seller = makeAddr("seller");
    uint256 constant BUY_KEY = 0xB00;
    uint256 constant SELL_KEY = 0x5E11;
    address relayer;

    function setUp() public {
        vm.warp(1_000);
        token = new MockUSDC("test", "USDC");
        oracle = new IndexOracleConsumer(address(this), vm.addr(KEY), 100, 60);
        ledger = new AtomicTradeLedger(
            address(this), address(token), address(oracle), vm.addr(KEY), 60, 1_000, 60
        );
        relayer = makeAddr("relayer");
        executor = new SignedOrderExecutor(address(ledger), relayer);
        ledger.bindExecutor(address(executor));
        ledger.registerBasket(BASKET, 1_100);
        token.mint(buyer, 100_000_000);
        token.mint(seller, 100_000_000);
        vm.startPrank(buyer);
        token.approve(address(ledger), 100_000_000);
        ledger.deposit(100_000_000);
        vm.stopPrank();
        vm.startPrank(seller);
        token.approve(address(ledger), 100_000_000);
        ledger.deposit(100_000_000);
        vm.stopPrank();
        _push(50, block.timestamp);
    }

    function _sign(string memory domain, address target, bytes32 data) internal view returns (bytes memory) {
        bytes32 separator = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes(domain)), keccak256("1"), block.chainid, target
        ));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(KEY, keccak256(abi.encodePacked("\x19\x01", separator, data)));
        return abi.encodePacked(r, s, v);
    }

    function _push(uint256 price, uint256 timestamp) internal {
        bytes32 data = keccak256(abi.encode(
            keccak256("PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"),
            BASKET, price, timestamp
        ));
        oracle.pushPrice(BASKET, price, timestamp, _sign("Xleuth Index Oracle", address(oracle), data));
    }

    function _leg(address trader) internal pure returns (IAtomicTradeLedger.Leg memory) {
        bytes memory intent = abi.encode(
            uint8(0), uint256(0), bytes32(0), bytes32(0), bytes32(uint256(uint160(trader)))
        );
        return IAtomicTradeLedger.Leg(trader, 5, keccak256(intent), bytes32(0), false, false, intent);
    }

    function _open() internal {
        vm.prank(address(executor));
        ledger.executeMatchedTrade(BASKET, _leg(buyer), _leg(seller), 1_000_000, 50_000);
    }

    function _closer(address trader, uint8 kind, uint256 trigger, bytes32 group)
        internal pure returns (IAtomicTradeLedger.Leg memory)
    {
        bytes32 id = bytes32(uint256(1)); // first lot of BASKET
        bytes memory intent = abi.encode(
            kind, trigger, group, id, bytes32(uint256(uint160(trader)))
        );
        return IAtomicTradeLedger.Leg(
            trader, 5, keccak256(intent), id, true, kind != 0, intent
        );
    }

    function _fund(address trader) internal {
        token.mint(trader, 100_000_000);
        vm.startPrank(trader);
        token.approve(address(ledger), 100_000_000);
        ledger.deposit(100_000_000);
        vm.stopPrank();
    }

    function _settle(uint256 price) internal {
        vm.warp(1_100);
        bytes32 data = keccak256(abi.encode(
            keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"),
            BASKET, price, block.timestamp
        ));
        ledger.startSettlement(
            BASKET, price, block.timestamp,
            _sign("Xleuth Atomic Settlement", address(ledger), data)
        );
    }

    function test_UnpairedOrUnauthenticatedWritesCannotCreateAClaim() public {
        vm.prank(buyer);
        vm.expectRevert(AtomicTradeLedger.Unauthorized.selector);
        ledger.executeMatchedTrade(BASKET, _leg(buyer), _leg(seller), 1_000_000, 50_000);
        assertEq(ledger.freeBalance(buyer), 100_000_000);
    }

    function test_ReservesWorstCaseLossAndPayoutsConserveCollateral() public {
        _open();
        assertEq(ledger.reservedBalance(buyer), 50_000_000);
        assertEq(ledger.reservedBalance(seller), 50_000_000);
        vm.prank(buyer);
        vm.expectRevert(AtomicTradeLedger.InsufficientBalance.selector);
        ledger.withdraw(50_000_001);
        _settle(80_000);
        ledger.settleBatch(BASKET, 1);
        assertEq(ledger.freeBalance(buyer), 130_000_000);
        assertEq(ledger.freeBalance(seller), 70_000_000);
        assertEq(token.balanceOf(address(ledger)), 200_000_000);
        assertTrue(ledger.isSettled(BASKET));
    }

    function test_ZeroResolutionIsValidAndBatched() public {
        _open();
        _open();
        _settle(0);
        ledger.settleBatch(BASKET, 1);
        assertFalse(ledger.isSettled(BASKET));
        assertEq(ledger.settlementCursor(BASKET), 1);
        ledger.settleBatch(BASKET, 1);
        assertTrue(ledger.isSettled(BASKET));
        assertEq(ledger.freeBalance(buyer), 0);
        assertEq(ledger.freeBalance(seller), 200_000_000);
    }

    function testFuzz_AnyFinalPricePreservesDepositorClaims(uint256 realized) public {
        realized = bound(realized, 0, 100_000);
        _open();
        _settle(realized);
        ledger.settleBatch(BASKET, 1);
        uint256 buyerClaim = ledger.freeBalance(buyer);
        uint256 sellerClaim = ledger.freeBalance(seller);
        assertEq(buyerClaim + sellerClaim, token.balanceOf(address(ledger)));
        assertEq(ledger.reservedBalance(buyer) + ledger.reservedBalance(seller), 0);
    }

    function test_InsufficientWorstCaseReserveFailsAtomically() public {
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.InsufficientBalance.selector);
        ledger.executeMatchedTrade(BASKET, _leg(buyer), _leg(seller), 3_000_000, 50_000);
        assertEq(ledger.lotCount(BASKET), 0);
    }

    function test_FutureOracleTimestampRejected() public {
        _push(50, block.timestamp + 1_000);
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.StalePrice.selector);
        ledger.executeMatchedTrade(BASKET, _leg(buyer), _leg(seller), 1_000_000, 50_000);
    }

    function test_ReduceOnlyAndUnknownIntentsFailClosed() public {
        IAtomicTradeLedger.Leg memory buy = _leg(buyer);
        buy.reduceOnly = true;
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.UnsupportedIntent.selector);
        ledger.executeMatchedTrade(BASKET, buy, _leg(seller), 1_000_000, 50_000);
    }

    function test_ExpiredBasketCannotOpenAndCannotSettleEarly() public {
        _open();
        bytes32 data = keccak256(abi.encode(
            keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"),
            BASKET, uint256(50_000), block.timestamp
        ));
        vm.expectRevert(AtomicTradeLedger.InvalidSettlement.selector);
        ledger.startSettlement(
            BASKET, 50_000, block.timestamp,
            _sign("Xleuth Atomic Settlement", address(ledger), data)
        );
        vm.warp(1_100);
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.InvalidBasket.selector);
        ledger.executeMatchedTrade(BASKET, _leg(buyer), _leg(seller), 1_000_000, 50_000);
    }

    function test_FutureDatedSettlementSignatureRejected() public {
        vm.warp(1_100);
        uint256 future = block.timestamp + 1;
        bytes32 data = keccak256(abi.encode(
            keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"),
            BASKET, uint256(50_000), future
        ));
        vm.expectRevert(AtomicTradeLedger.InvalidSettlement.selector);
        ledger.startSettlement(
            BASKET, 50_000, future,
            _sign("Xleuth Atomic Settlement", address(ledger), data)
        );
    }

    function test_BindingCannotBeReassigned() public {
        vm.expectRevert(AtomicTradeLedger.InvalidConfiguration.selector);
        ledger.bindExecutor(address(executor));
    }

    function test_MarketRequiresSignedFillOrKillAndStopRequiresTrigger() public {
        IAtomicTradeLedger.Leg memory buy = _leg(buyer);
        buy.intent = abi.encode(uint8(1), uint256(0), bytes32(0), bytes32(0), bytes32(uint256(123)));
        buy.orderId = keccak256(buy.intent);
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.UnsupportedIntent.selector);
        ledger.executeMatchedTrade(BASKET, buy, _leg(seller), 1_000_000, 50_000);

        buy.fillOrKill = true;
        buy.intent = abi.encode(uint8(2), uint256(60_000), bytes32(0), bytes32(0), bytes32(uint256(123)));
        buy.orderId = keccak256(buy.intent);
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.UnsupportedIntent.selector);
        ledger.executeMatchedTrade(BASKET, buy, _leg(seller), 1_000_000, 50_000);

        buy.intent = abi.encode(uint8(2), uint256(50_000), bytes32(0), bytes32(0), bytes32(uint256(123)));
        buy.orderId = keccak256(buy.intent);
        vm.prank(address(executor));
        ledger.executeMatchedTrade(BASKET, buy, _leg(seller), 1_000_000, 50_000);
        assertEq(ledger.lotCount(BASKET), 1);
    }

    function test_FullLongCloseTransfersCollateralAndInvalidatesAttachedSibling() public {
        _open();
        address newLong = makeAddr("new-long");
        _fund(newLong);
        IAtomicTradeLedger.Leg memory stop = _closer(buyer, 3, 50_000, bytes32(uint256(777)));
        vm.prank(address(executor));
        ledger.executeMatchedTrade(BASKET, _leg(newLong), stop, 1_000_000, 50_000);
        assertEq(ledger.freeBalance(buyer), 100_000_000);
        assertEq(ledger.reservedBalance(buyer), 0);
        assertEq(ledger.getLot(BASKET, 0).buyer, newLong);
        // A take-profit signed against the same position cannot execute now.
        IAtomicTradeLedger.Leg memory takeProfit = _closer(buyer, 4, 50_000, bytes32(uint256(777)));
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.UnsupportedIntent.selector);
        ledger.executeMatchedTrade(BASKET, _leg(newLong), takeProfit, 1_000_000, 50_000);
        _settle(0);
        ledger.settleBatch(BASKET, 1);
        assertEq(ledger.freeBalance(newLong), 50_000_000);
        assertEq(ledger.freeBalance(seller), 150_000_000);
        assertEq(ledger.freeBalance(buyer), 100_000_000);
    }

    function test_PartialShortCloseSplitsLotWithoutCreatingUnbackedClaims() public {
        _open();
        address newShort = makeAddr("new-short");
        _fund(newShort);
        vm.prank(address(executor));
        ledger.executeMatchedTrade(
            BASKET, _closer(seller, 0, 0, bytes32(0)), _leg(newShort), 400_000, 50_000
        );
        assertEq(ledger.lotCount(BASKET), 2);
        assertEq(ledger.getLot(BASKET, 0).size, 600_000);
        assertEq(ledger.getLot(BASKET, 1).size, 400_000);
        assertEq(ledger.reservedBalance(seller), 30_000_000);
        assertEq(ledger.freeBalance(seller), 70_000_000);
        _settle(0);
        ledger.settleBatch(BASKET, 1);
        assertFalse(ledger.isSettled(BASKET));
        ledger.settleBatch(BASKET, 1);
        assertEq(ledger.freeBalance(buyer) + ledger.freeBalance(seller)
            + ledger.freeBalance(newShort), token.balanceOf(address(ledger)));
    }

    function test_BracketCannotPartiallyCloseOrTransferAnotherTradersLot() public {
        _open();
        address entrant = makeAddr("entrant");
        _fund(entrant);
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.UnsupportedIntent.selector);
        ledger.executeMatchedTrade(
            BASKET, _leg(entrant), _closer(buyer, 3, 50_000, bytes32(uint256(7))),
            500_000, 50_000
        );
        vm.prank(address(executor));
        vm.expectRevert(AtomicTradeLedger.UnsupportedIntent.selector);
        ledger.executeMatchedTrade(
            BASKET, _leg(seller), _closer(entrant, 0, 0, bytes32(0)),
            1_000_000, 50_000
        );
    }

    function testFuzz_PartialReplacementConservesAllCollateral(
        bool closeLong, uint256 part, uint256 executionPrice, uint256 realized
    ) public {
        part = bound(part, 1, 1_000_000);
        executionPrice = bound(executionPrice, 49_000, 51_000);
        realized = bound(realized, 0, 100_000);
        _open();
        address entrant = makeAddr("new-counterparty");
        _fund(entrant);
        vm.prank(address(executor));
        if (closeLong) {
            ledger.executeMatchedTrade(
                BASKET, _leg(entrant), _closer(buyer, 0, 0, bytes32(0)),
                part, executionPrice
            );
        } else {
            ledger.executeMatchedTrade(
                BASKET, _closer(seller, 0, 0, bytes32(0)), _leg(entrant),
                part, executionPrice
            );
        }
        _settle(realized);
        ledger.settleBatch(BASKET, 10);
        assertEq(
            ledger.freeBalance(buyer) + ledger.freeBalance(seller) + ledger.freeBalance(entrant),
            token.balanceOf(address(ledger))
        );
        assertEq(
            ledger.reservedBalance(buyer) + ledger.reservedBalance(seller)
                + ledger.reservedBalance(entrant), 0
        );
    }

    function _signOrder(SignedOrderExecutor.Authorization memory a, uint256 key)
        internal view returns (bytes memory)
    {
        bytes32 typeHash = keccak256(
            "Authorization(address trader,bytes32 basketId,bytes32 orderId,uint8 side,uint256 size,uint256 maxNotional,uint256 minPrice,uint256 maxPrice,uint256 leverage,uint256 nonce,uint256 deadline,bool fillOrKill,bool reduceOnly,bytes32 positionId)"
        );
        bytes32 domain = keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256("Xleuth Orders"), keccak256("2"), block.chainid, address(executor)
        ));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domain, keccak256(abi.encode(typeHash, a))));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    function test_RealSignedExecutorMovesBothSidesAtomically() public {
        // A true end-to-end match must use signer addresses as funded traders.
        address longUser = vm.addr(BUY_KEY);
        address shortUser = vm.addr(SELL_KEY);
        token.mint(longUser, 50_000_000);
        token.mint(shortUser, 50_000_000);
        vm.startPrank(longUser);
        token.approve(address(ledger), 50_000_000);
        ledger.deposit(50_000_000);
        vm.stopPrank();
        vm.startPrank(shortUser);
        token.approve(address(ledger), 50_000_000);
        ledger.deposit(50_000_000);
        vm.stopPrank();

        IAtomicTradeLedger.Leg memory longLeg = _leg(longUser);
        IAtomicTradeLedger.Leg memory shortLeg = _leg(shortUser);
        SignedOrderExecutor.Authorization memory buy = SignedOrderExecutor.Authorization(
            longUser, BASKET, longLeg.orderId, 0, 1_000_000, 50_000_000,
            50_000, 50_000, 5, 1, 1_050, true, false, bytes32(0)
        );
        SignedOrderExecutor.Authorization memory sell = SignedOrderExecutor.Authorization(
            shortUser, BASKET, shortLeg.orderId, 1, 1_000_000, 50_000_000,
            50_000, 50_000, 5, 1, 1_050, true, false, bytes32(0)
        );
        vm.prank(relayer);
        executor.executeMatch(SignedOrderExecutor.Match(
            buy, _signOrder(buy, BUY_KEY), sell, _signOrder(sell, SELL_KEY),
            1_000_000, 50_000, longLeg.intent, shortLeg.intent
        ));
        assertEq(ledger.lotCount(BASKET), 1);
        assertEq(ledger.reservedBalance(longUser), 50_000_000);
        assertEq(ledger.reservedBalance(shortUser), 50_000_000);
    }
}
