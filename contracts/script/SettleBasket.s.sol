// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {SettlementEngine} from "../src/SettlementEngine.sol";

/// @title SettleBasket
/// @notice Registers a basket expiry and/or settles a basket on Amoy at a
///         signed realized YES fraction, exactly as the Week-4 settlement
///         service would. Reads from contracts/.env:
///           SETTLEMENT_ENGINE_ADDRESS (required)
///           SETTLEMENT_SIGNER_PRIVATE_KEY (falls back to DEPLOYER_PRIVATE_KEY)
///           BASKET_NAME (e.g. TOP20-JULY)
///           BASKET_EXPIRY_SECONDS (unix; required to register the expiry)
///           REALIZED_PRICE (0-100 index points, required to settle)
///         Settling requires block.timestamp >= the basket's registered expiry
///         (SettlementEngine.NotExpired) and a fresh, authorized signature.
///         Usage:
///           forge script script/SettleBasket.s.sol:SettleBasket \
///             --rpc-url $RPC_URL --private-key $DEPLOYER_PRIVATE_KEY --broadcast
contract SettleBasket is Script {
    function run() external {
        address engineAddr = vm.envAddress("SETTLEMENT_ENGINE_ADDRESS");
        string memory basketName = vm.envString("BASKET_NAME");
        bytes32 basketId = keccak256(bytes(basketName));
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        uint256 settleKey = vm.envOr("SETTLEMENT_SIGNER_PRIVATE_KEY", deployerKey);

        SettlementEngine engine = SettlementEngine(engineAddr);

        vm.startBroadcast(deployerKey);

        if (vm.envExists("BASKET_EXPIRY_SECONDS") && vm.envUint("BASKET_EXPIRY_SECONDS") != 0) {
            uint256 expiry = vm.envUint("BASKET_EXPIRY_SECONDS");
            engine.setBasketExpiry(basketId, expiry);
            console2.log("expiry registered for %s: %s", basketName, expiry);
        }

        if (vm.envExists("REALIZED_PRICE")) {
            uint256 realized = vm.envUint("REALIZED_PRICE");
            uint256 timestamp = block.timestamp;
            bytes memory sig = _signSettle(settleKey, engineAddr, basketId, realized, timestamp);
            engine.settleBasket(basketId, realized, timestamp, sig);
            console2.log(
                "settled %s at realized %s (tx block %s)",
                basketName, realized, block.number
            );
        }

        vm.stopBroadcast();
    }

    /// @dev Reads a private key from env, tolerating a missing 0x prefix.
    function _envPrivateKey(string memory name) internal returns (uint256) {
        string memory value = vm.envString(name);
        if (bytes(value).length >= 2 && bytes(value)[0] == "0" && bytes(value)[1] == "x") {
            return vm.parseUint(value);
        }
        return vm.parseUint(string.concat("0x", value));
    }

    /// @dev EIP-712 signature of SettleBasket(basketId, realizedPrice, timestamp)
    ///      for the SettlementEngine domain ("Xleuth Settlement","1").
    function _signSettle(
        uint256 key,
        address engineAddr,
        bytes32 basketId,
        uint256 realized,
        uint256 timestamp
    ) internal view returns (bytes memory) {
        bytes32 typeHash =
            keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)");
        bytes32 structHash = keccak256(abi.encode(typeHash, basketId, realized, timestamp));
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Settlement"),
                keccak256("1"),
                block.chainid,
                engineAddr
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }
}