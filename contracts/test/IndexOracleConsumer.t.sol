// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";

contract IndexOracleConsumerTest is Test {
    IndexOracleConsumer oracle;

    uint256 constant CHAIN_ID = 31337;
    uint256 constant PRICE_SCALE = 100;

    address owner = makeAddr("owner");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    uint256 oracleKey = 0xABCD;
    address oracleSigner = vm.addr(oracleKey);

    bytes32 basketA = keccak256("TOP20-JULY");
    bytes32 basketB = keccak256("TOP20-AUGUST");

    function setUp() public {
        oracle = new IndexOracleConsumer(owner, oracleSigner, PRICE_SCALE, 60);
    }

    function _sign(uint256 key, bytes32 basketId, uint256 price, uint256 timestamp)
        internal
        view
        returns (bytes memory)
    {
        bytes32 typeHash =
            keccak256("PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)");
        bytes32 structHash = keccak256(abi.encode(typeHash, basketId, price, timestamp));
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
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    // ── Authorized pushes ──────────────────────────────────────────────────

    function test_AuthorizedOracle_PushesPrice() public {
        vm.warp(1_000);
        bytes memory sig = _sign(oracleKey, basketA, 64, 1_000);

        vm.expectEmit(true, true, true, true, address(oracle));
        emit IndexOracleConsumer.PriceUpdated(basketA, 64, 1_000, oracleSigner);
        oracle.pushPrice(basketA, 64, 1_000, sig);

        (uint256 price, uint256 timestamp) = oracle.priceOf(basketA);
        assertEq(price, 64);
        assertEq(timestamp, 1_000);
    }

    function test_MultipleBaskets_AreIndependent() public {
        vm.warp(1_000);
        oracle.pushPrice(basketA, 40, 1_000, _sign(oracleKey, basketA, 40, 1_000));
        vm.warp(1_100);
        oracle.pushPrice(basketB, 55, 1_100, _sign(oracleKey, basketB, 55, 1_100));

        (uint256 pa,) = oracle.priceOf(basketA);
        (uint256 pb,) = oracle.priceOf(basketB);
        assertEq(pa, 40);
        assertEq(pb, 55);
    }

    function test_Fuzz_PushVariousPrices(uint8 price, uint64 ts) public {
        vm.assume(price > 0 && price <= PRICE_SCALE);
        vm.assume(ts > 0); // ts == 0 collides with the unset-price sentinel
        vm.warp(ts);
        oracle.pushPrice(basketA, price, ts, _sign(oracleKey, basketA, price, ts));

        (uint256 storedPrice, uint256 storedTs) = oracle.priceOf(basketA);
        assertEq(storedPrice, price);
        assertEq(storedTs, ts);
    }

    // ── Unauthorized signer rejection ──────────────────────────────────────

    function test_UnauthorizedSigner_Reverts() public {
        vm.warp(1_000);
        bytes memory sig = _sign(0xBEEF, basketA, 64, 1_000);

        vm.expectRevert(IndexOracleConsumer.UnauthorizedSigner.selector);
        oracle.pushPrice(basketA, 64, 1_000, sig);

        (uint256 price, uint256 timestamp) = oracle.priceOf(basketA);
        assertEq(price, 0);
        assertEq(timestamp, 0);
    }

    function test_ArbitraryUserCall_WithValidSignature_Accepted() public {
        vm.warp(1_000);
        bytes memory sig = _sign(oracleKey, basketA, 64, 1_000);

        // Authorization is signer-based, not caller-based: any caller may push
        // an update as long as it carries the authorized oracle's signature.
        vm.prank(alice);
        oracle.pushPrice(basketA, 64, 1_000, sig);

        (uint256 price,) = oracle.priceOf(basketA);
        assertEq(price, 64);
    }

    function test_TamperedSignature_Reverts() public {
        vm.warp(1_000);
        bytes memory sig = _sign(oracleKey, basketA, 64, 1_000);

        vm.expectRevert();
        oracle.pushPrice(basketA, 65, 1_000, sig);
    }

    // ── Stale / out-of-order rejection ─────────────────────────────────────

    function test_OutOfOrderUpdate_Reverts() public {
        vm.warp(1_000);
        oracle.pushPrice(basketA, 64, 1_000, _sign(oracleKey, basketA, 64, 1_000));

        vm.warp(1_100);
        bytes memory stale = _sign(oracleKey, basketA, 65, 1_000);
        vm.expectRevert(IndexOracleConsumer.StaleUpdate.selector);
        oracle.pushPrice(basketA, 65, 1_000, stale);
    }

    function test_ReplayOfLastUpdate_Reverts() public {
        vm.warp(1_000);
        bytes memory sig = _sign(oracleKey, basketA, 64, 1_000);
        oracle.pushPrice(basketA, 64, 1_000, sig);

        vm.warp(2_000);
        vm.expectRevert(IndexOracleConsumer.StaleUpdate.selector);
        oracle.pushPrice(basketA, 64, 1_000, sig);
    }

    function test_UpdateOlderThanStalenessWindow_Reverts() public {
        vm.warp(1_000);
        oracle.pushPrice(basketA, 64, 1_000, _sign(oracleKey, basketA, 64, 1_000));

        // New update signed at t=1930 but submitted at block.timestamp=2000:
        // 1930 + 60 = 1990 < 2000 -> too old to accept.
        vm.warp(2_000);
        vm.expectRevert(IndexOracleConsumer.StaleUpdate.selector);
        oracle.pushPrice(basketA, 66, 1_930, _sign(oracleKey, basketA, 66, 1_930));
    }

    function test_UpdateWithinStalenessWindow_Accepted() public {
        vm.warp(1_000);
        oracle.pushPrice(basketA, 64, 1_000, _sign(oracleKey, basketA, 64, 1_000));

        vm.warp(1_000 + 60);
        oracle.pushPrice(basketA, 66, 1_000 + 60, _sign(oracleKey, basketA, 66, 1_000 + 60));
        (uint256 price,) = oracle.priceOf(basketA);
        assertEq(price, 66);
    }

    // ── Price bounds ───────────────────────────────────────────────────────

    function test_ZeroPrice_Reverts() public {
        vm.warp(1_000);
        vm.expectRevert(IndexOracleConsumer.PriceOutOfRange.selector);
        oracle.pushPrice(basketA, 0, 1_000, _sign(oracleKey, basketA, 0, 1_000));
    }

    function test_PriceAboveScale_Reverts() public {
        vm.warp(1_000);
        vm.expectRevert(IndexOracleConsumer.PriceOutOfRange.selector);
        oracle.pushPrice(
            basketA, PRICE_SCALE + 1, 1_000, _sign(oracleKey, basketA, PRICE_SCALE + 1, 1_000)
        );
    }

    // ── Access control ─────────────────────────────────────────────────────

    function test_SetAuthorizedOracle_RotatesSigner() public {
        vm.warp(1_000);
        address newSigner = vm.addr(0x1234);
        vm.prank(owner);
        oracle.setAuthorizedOracle(newSigner);

        bytes memory oldSig = _sign(oracleKey, basketA, 64, 1_000);
        vm.expectRevert(IndexOracleConsumer.UnauthorizedSigner.selector);
        oracle.pushPrice(basketA, 64, 1_000, oldSig);

        oracle.pushPrice(basketA, 70, 1_000, _sign(0x1234, basketA, 70, 1_000));
        (uint256 price,) = oracle.priceOf(basketA);
        assertEq(price, 70);
    }

    function test_SetAuthorizedOracle_OnlyOwner() public {
        vm.prank(bob);
        vm.expectRevert();
        oracle.setAuthorizedOracle(bob);
    }

    function test_SetMaxStaleness_OnlyOwner() public {
        vm.prank(bob);
        vm.expectRevert();
        oracle.setMaxStaleness(120);
    }
}
