// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";

/// @notice Cross-checks the Python oracle-service signature against Solidity's
///         own EIP-712 computation. The Python oracle-service signs
///         PriceUpdate(basketId, price, timestamp) for IndexOracleConsumer with
///         domain ("Xleuth Index Oracle","1"). We reproduce that exact digest
///         in Solidity and ecrecover the Python-computed signature, asserting
///         it resolves to the Python signer key — proving the Python EIP-712
///         layout is byte-for-byte compatible with on-chain verification.
///
///         Python inputs (fixed fixture, not secrets):
///           key        = 0x1111...1111 (x32)
///           consumer   = 0x00000000000000000000000000000000000000ab
///           chainId    = 80002
///           basketName = "TOP20-JULY"
///           price      = 50
///           timestamp  = 1_700_000_000
///         Python produced signature r = 0xf05a..., s = 0x6c8c..., v = 0x1b.
contract OracleServiceCrossCheckTest is Test {
    uint256 constant CHAIN_ID = 80002;

    function test_PythonSignature_RecoversToPythonSigner() external {
        bytes32 basketId = keccak256("TOP20-JULY");
        uint256 price = 50;
        uint256 timestamp = 1_700_000_000;

        bytes32 typeHash = keccak256(
            "PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"
        );
        bytes32 structHash = keccak256(abi.encode(typeHash, basketId, price, timestamp));
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Index Oracle"),
                keccak256("1"),
                CHAIN_ID,
                address(0xAB) // consumer address used in Python
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));

        bytes32 r = 0xf05aa2f92a6d9201a1cb3dca6546cad6421088b2d9779570572ba10afe95a18a;
        bytes32 s = 0x6c8c6e2e564550f3b51440f518dd7b87f451060cc5da717be1b90ae3f229a35a;
        uint8 v = 0x1b;

        address recovered = ecrecover(digest, v, r, s);
        console.log("recovered:", recovered);
        assertEq(
            recovered,
            0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A,
            "Python-signed price update must recover to the Python signer"
        );
    }
}