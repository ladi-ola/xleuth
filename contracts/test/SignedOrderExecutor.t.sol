// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IERC1271} from "@openzeppelin/contracts/interfaces/IERC1271.sol";
import {SignedOrderExecutor, IAtomicTradeLedger} from "../src/SignedOrderExecutor.sol";

/// @dev Test-only transactional harness, NOT a collateral/position manager.
contract AtomicLedgerHarness is IAtomicTradeLedger {
    address public executor;
    uint256 public calls;
    uint256 public failOnCall;
    mapping(address => uint256) public bought;
    mapping(address => uint256) public sold;

    function executionProtocol() external pure returns (bytes32) {
        return keccak256("Xleuth Atomic Ledger v2");
    }

    function configure(address executor_, uint256 failOnCall_) external {
        executor = executor_;
        failOnCall = failOnCall_;
    }

    function executeMatchedTrade(
        bytes32,
        Leg calldata buy,
        Leg calldata sell,
        uint256 size,
        uint256
    ) external {
        require(msg.sender == executor, "executor only");
        ++calls;
        bought[buy.trader] += size;
        require(calls != failOnCall, "synthetic second-leg failure");
        sold[sell.trader] += size;
    }
}

contract SignatureWalletHarness is IERC1271 {
    mapping(bytes32 => bool) public approved;

    function setApproved(bytes32 digest, bool valid) external {
        approved[digest] = valid;
    }

    function isValidSignature(bytes32 digest, bytes memory) external view returns (bytes4) {
        return approved[digest] ? IERC1271.isValidSignature.selector : bytes4(0xffffffff);
    }
}

contract SignedOrderExecutorTest is Test {
    SignedOrderExecutor executor;
    AtomicLedgerHarness ledger;
    uint256 constant BUY_KEY = 0xA11CE; // Synthetic local keys only.
    uint256 constant SELL_KEY = 0xB0B;
    address buyer = vm.addr(BUY_KEY);
    address seller = vm.addr(SELL_KEY);
    address relayer = makeAddr("relayer");
    bytes32 constant BASKET = keccak256("top20-2027-01");

    function setUp() public {
        vm.warp(1_000);
        ledger = new AtomicLedgerHarness();
        executor = new SignedOrderExecutor(address(ledger), relayer);
        ledger.configure(address(executor), 0);
    }

    function _authorization(bool buy)
        internal
        view
        returns (SignedOrderExecutor.Authorization memory)
    {
        return SignedOrderExecutor.Authorization({
            trader: buy ? buyer : seller,
            basketId: BASKET,
            orderId: keccak256(bytes(buy ? "buy intent" : "sell intent")),
            side: buy ? 0 : 1,
            size: 1_000_000,
            maxNotional: 50_000_000,
            minPrice: 1,
            maxPrice: 100_000,
            leverage: 5,
            nonce: 7,
            deadline: 2_000,
            fillOrKill: false,
            reduceOnly: false,
            positionId: bytes32(0)
        });
    }

    function _sign(SignedOrderExecutor.Authorization memory a, uint256 key)
        internal
        view
        returns (bytes memory)
    {
        bytes32 typeHash = keccak256(
            "Authorization(address trader,bytes32 basketId,bytes32 orderId,uint8 side,uint256 size,uint256 maxNotional,uint256 minPrice,uint256 maxPrice,uint256 leverage,uint256 nonce,uint256 deadline,bool fillOrKill,bool reduceOnly,bytes32 positionId)"
        );
        bytes32 domain = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Orders"),
                keccak256("2"),
                block.chainid,
                address(executor)
            )
        );
        bytes32 digest =
            keccak256(abi.encodePacked("\x19\x01", domain, keccak256(abi.encode(typeHash, a))));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    function _execute(
        SignedOrderExecutor.Authorization memory buy,
        SignedOrderExecutor.Authorization memory sell,
        uint256 size,
        uint256 price
    ) internal {
        bytes memory bs = _sign(buy, BUY_KEY);
        bytes memory ss = _sign(sell, SELL_KEY);
        vm.prank(relayer);
        executor.executeMatch(
            SignedOrderExecutor.Match(
                buy,
                bs,
                sell,
                ss,
                size,
                price,
                buy.orderId == keccak256("changed intent")
                    ? bytes("changed intent")
                    : bytes("buy intent"),
                bytes("sell intent")
            )
        );
    }

    function test_ValidPair_UsesOneAtomicLedgerCallAndExactUnits() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        buy.maxNotional = 51_000_000;
        sell.maxNotional = 51_000_000;
        _execute(buy, sell, 200_000, 50_123);
        assertEq(ledger.calls(), 1);
        assertEq(ledger.bought(buyer), 200_000);
        assertEq(ledger.sold(seller), 200_000);
        assertEq(executor.filledSize(executor.hashAuthorization(buy)), 200_000);
        assertEq(executor.filledNotional(executor.hashAuthorization(buy)), 10_024_600);
    }

    function test_ReplayCannotOverfill() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        _execute(buy, sell, buy.size, 50_000);
        vm.expectRevert(SignedOrderExecutor.SizeExceeded.selector);
        _execute(buy, sell, buy.size, 50_000);
        assertEq(ledger.calls(), 1);
    }

    function test_LimitOrderCanPartiallyFillBelowTenDollars() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        buy.size = 200_000;
        sell.size = 200_000;
        buy.maxNotional = 10_000_000;
        sell.maxNotional = 10_000_000;
        _execute(buy, sell, 50_000, 50_000);
        _execute(buy, sell, 150_000, 50_000);
        assertEq(ledger.bought(buyer), 200_000);
    }

    function test_PartialFillStillHonorsCumulativeNotionalBudget() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        _execute(buy, sell, 500_000, 50_000);
        vm.expectRevert(SignedOrderExecutor.NotionalExceeded.selector);
        _execute(buy, sell, 500_000, 51_000);
        assertEq(ledger.calls(), 1);
    }

    function test_MinimumNotionalBoundary() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        buy.size = 200_000;
        sell.size = 200_000;
        _execute(buy, sell, 200_000, 50_000);
    }

    function test_BelowMinimumNotionalRejected() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        buy.size = 199_999;
        sell.size = 199_999;
        vm.expectRevert(SignedOrderExecutor.NotionalBelowMinimum.selector);
        _execute(buy, sell, buy.size, 50_000);
    }

    function test_MaximumNotionalBoundary() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        buy.size = 20_000_000;
        sell.size = 20_000_000;
        buy.maxNotional = 1_000_000_000;
        sell.maxNotional = 1_000_000_000;
        _execute(buy, sell, buy.size, 50_000);
        assertEq(executor.filledNotional(executor.hashAuthorization(buy)), 1_000_000_000);
    }

    function test_AboveMaximumNotionalRejected() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        buy.maxNotional = 1_000_000_001;
        vm.expectRevert(SignedOrderExecutor.InvalidAuthorization.selector);
        _execute(buy, sell, buy.size, 50_000);
    }

    function test_TamperingWithAnySignedFieldInvalidatesSignature() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        bytes memory bs = _sign(buy, BUY_KEY);
        bytes memory ss = _sign(sell, SELL_KEY);
        buy.leverage = 4;
        vm.prank(relayer);
        vm.expectRevert(SignedOrderExecutor.InvalidSignature.selector);
        executor.executeMatch(
            SignedOrderExecutor.Match(
                buy, bs, sell, ss, buy.size, 50_000, bytes("buy intent"), bytes("sell intent")
            )
        );
    }

    function test_WrongSignerRejected() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        vm.expectRevert(SignedOrderExecutor.InvalidSignature.selector);
        executor.validateAuthorization(buy, _sign(buy, SELL_KEY));
    }

    function test_ExpiredSignatureRejected() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        vm.warp(buy.deadline + 1);
        vm.expectRevert(SignedOrderExecutor.AuthorizationExpired.selector);
        executor.validateAuthorization(buy, _sign(buy, BUY_KEY));
    }

    function test_SignatureValidAtExactDeadline() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        vm.warp(buy.deadline);
        executor.validateAuthorization(buy, _sign(buy, BUY_KEY));
    }

    function test_CancelledNonceCannotExecute() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        vm.prank(buyer);
        executor.cancelNonce(buy.nonce);
        vm.expectRevert(SignedOrderExecutor.AuthorizationCancelled.selector);
        _execute(buy, _authorization(false), buy.size, 50_000);
        assertEq(ledger.calls(), 0);
    }

    function test_OtherAccountCannotCancelTradersNonce() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        vm.prank(seller);
        executor.cancelNonce(buy.nonce);
        // The seller's own nonce is now cancelled; buyer's remains usable.
        executor.validateAuthorization(buy, _sign(buy, BUY_KEY));
    }

    function test_MinimumNonceInvalidatesOldIntents() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        vm.prank(buyer);
        executor.raiseMinimumNonce(8);
        vm.expectRevert(SignedOrderExecutor.AuthorizationCancelled.selector);
        executor.validateAuthorization(buy, _sign(buy, BUY_KEY));
    }

    function test_NonceCannotBeReusedForChangedIntent() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        _execute(buy, sell, 500_000, 50_000);
        buy.orderId = keccak256("changed intent");
        vm.expectRevert(SignedOrderExecutor.NonceAlreadyBound.selector);
        _execute(buy, sell, 500_000, 50_000);
    }

    function test_SecondLegRevertRollsBackBothLedgerAndAuthorizationState() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        ledger.configure(address(executor), 1);
        vm.expectRevert("synthetic second-leg failure");
        _execute(buy, sell, buy.size, 50_000);
        assertEq(ledger.bought(buyer), 0);
        assertEq(ledger.sold(seller), 0);
        assertEq(ledger.calls(), 0);
        assertEq(executor.filledSize(executor.hashAuthorization(buy)), 0);
        assertEq(executor.nonceDigest(buyer, buy.nonce), bytes32(0));
    }

    function test_OnlyConfiguredRelayerMayExecute() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        bytes memory bs = _sign(buy, BUY_KEY);
        bytes memory ss = _sign(sell, SELL_KEY);
        vm.expectRevert(SignedOrderExecutor.InvalidRelayer.selector);
        executor.executeMatch(
            SignedOrderExecutor.Match(
                buy, bs, sell, ss, buy.size, 50_000, bytes("buy intent"), bytes("sell intent")
            )
        );
    }

    function test_CrossBasketAndSelfTradeRejected() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        sell.basketId = keccak256("different basket");
        vm.expectRevert(SignedOrderExecutor.InvalidMatch.selector);
        _execute(buy, sell, buy.size, 50_000);
        sell = _authorization(false);
        sell.trader = buyer;
        vm.expectRevert(SignedOrderExecutor.InvalidMatch.selector);
        _execute(buy, sell, buy.size, 50_000);
    }

    function test_PriceOutsideSignedBoundsRejected() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        buy.maxPrice = 49_999;
        vm.expectRevert(SignedOrderExecutor.PriceOutsideAuthorization.selector);
        _execute(buy, _authorization(false), buy.size, 50_000);
    }

    function test_ReduceOnlyMustBindPositionIdentifier() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        buy.reduceOnly = true;
        vm.expectRevert(SignedOrderExecutor.InvalidAuthorization.selector);
        executor.validateAuthorization(buy, _sign(buy, BUY_KEY));
    }

    function test_ERC1271SignatureRevocationIsCheckedForEveryFill() public {
        SignatureWalletHarness wallet = new SignatureWalletHarness();
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        buy.trader = address(wallet);
        bytes32 digest = executor.hashAuthorization(buy);
        wallet.setApproved(digest, true);
        executor.validateAuthorization(buy, hex"1234");
        wallet.setApproved(digest, false);
        vm.expectRevert(SignedOrderExecutor.InvalidSignature.selector);
        executor.validateAuthorization(buy, hex"1234");
    }

    function test_SignaturesCannotReplayOnAnotherExecutorOrChain() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        bytes memory signature = _sign(buy, BUY_KEY);
        SignedOrderExecutor other = new SignedOrderExecutor(address(ledger), relayer);
        vm.expectRevert(SignedOrderExecutor.InvalidSignature.selector);
        other.validateAuthorization(buy, signature);
        vm.chainId(block.chainid + 1);
        vm.expectRevert(SignedOrderExecutor.InvalidSignature.selector);
        executor.validateAuthorization(buy, signature);
    }

    function _batch() internal view returns (SignedOrderExecutor.Match[] memory matches) {
        matches = new SignedOrderExecutor.Match[](2);
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        buy.fillOrKill = true;
        for (uint256 i; i < 2; ++i) {
            SignedOrderExecutor.Authorization memory sell = _authorization(false);
            sell.nonce = i;
            bytes memory intent = abi.encode("maker", i);
            sell.orderId = keccak256(intent);
            matches[i] = SignedOrderExecutor.Match(
                buy,
                _sign(buy, BUY_KEY),
                sell,
                _sign(sell, SELL_KEY),
                500_000,
                50_000,
                bytes("buy intent"),
                intent
            );
        }
    }

    function test_FokAcrossMultipleMakersIsAtomic() public {
        SignedOrderExecutor.Match[] memory matches = _batch();
        vm.prank(relayer);
        executor.executeMatches(matches);
        assertEq(ledger.calls(), 2);
        assertEq(ledger.bought(buyer), 1_000_000);
    }

    function test_IncompleteFokRollsBackAllLedgerCalls() public {
        SignedOrderExecutor.Match[] memory matches = _batch();
        matches[1].size = 499_999;
        vm.prank(relayer);
        vm.expectRevert(SignedOrderExecutor.FillOrKillRequired.selector);
        executor.executeMatches(matches);
        assertEq(ledger.calls(), 0);
        assertEq(ledger.bought(buyer), 0);
        assertEq(executor.filledSize(executor.hashAuthorization(matches[0].buy)), 0);
    }

    function test_BatchLaterRevertRollsBackEarlierMatchedPair() public {
        SignedOrderExecutor.Match[] memory matches = _batch();
        ledger.configure(address(executor), 2);
        vm.prank(relayer);
        vm.expectRevert("synthetic second-leg failure");
        executor.executeMatches(matches);
        assertEq(ledger.calls(), 0);
        assertEq(ledger.bought(buyer), 0);
        assertEq(executor.nonceDigest(buyer, matches[0].buy.nonce), bytes32(0));
    }

    function test_FokSinglePairCannotPartiallyExecute() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        buy.fillOrKill = true;
        vm.expectRevert(SignedOrderExecutor.FillOrKillRequired.selector);
        _execute(buy, _authorization(false), 500_000, 50_000);
        assertEq(ledger.calls(), 0);
    }

    function test_ZeroCodeLedgerAddressCannotBeUsed() public {
        vm.expectRevert(SignedOrderExecutor.InvalidLedger.selector);
        new SignedOrderExecutor(makeAddr("no ledger"), relayer);
    }

    function test_OrdinaryContractCannotMasqueradeAsAtomicLedger() public {
        SignatureWalletHarness notLedger = new SignatureWalletHarness();
        vm.expectRevert(SignedOrderExecutor.InvalidLedger.selector);
        new SignedOrderExecutor(address(notLedger), relayer);
    }

    function test_IntentPreimageCannotBeSubstitutedByRelayer() public {
        SignedOrderExecutor.Authorization memory buy = _authorization(true);
        SignedOrderExecutor.Authorization memory sell = _authorization(false);
        SignedOrderExecutor.Match memory matched = SignedOrderExecutor.Match(
            buy,
            _sign(buy, BUY_KEY),
            sell,
            _sign(sell, SELL_KEY),
            buy.size,
            50_000,
            bytes("different trigger / OCO / order type"),
            bytes("sell intent")
        );
        vm.prank(relayer);
        vm.expectRevert(SignedOrderExecutor.IntentMismatch.selector);
        executor.executeMatch(matched);
        assertEq(ledger.calls(), 0);
    }

    function test_Eip712VectorMatchesPythonAndBrowser() public {
        vm.chainId(80002);
        address vectorAddress = 0x2222222222222222222222222222222222222222;
        // EIP712 rebuilds its domain at this address instead of using the
        // original deployment's cached separator. No funds/ledger calls.
        vm.etch(vectorAddress, address(executor).code);
        SignedOrderExecutor.Authorization memory a = SignedOrderExecutor.Authorization({
            trader: 0x1111111111111111111111111111111111111111,
            basketId: bytes32(
                uint256(0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)
            ),
            orderId: bytes32(
                uint256(0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb)
            ),
            side: 0,
            size: 1_234_567,
            maxNotional: 100_000_000,
            minPrice: 50_000,
            maxPrice: 50_001,
            leverage: 3,
            nonce: (uint256(1) << 80) + 7,
            deadline: 2_000_000_000,
            fillOrKill: false,
            reduceOnly: false,
            positionId: bytes32(0)
        });
        assertEq(
            SignedOrderExecutor(vectorAddress).hashAuthorization(a),
            0xdd4cdf2bedcadb6766b94138db28b3435cc8602f7cfe3efa8c97c4e1a4e877e7
        );
    }
}
