// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";

/// @title ConfigureBaskets
/// @notice Seeds signed index prices for the active baskets on-chain so the
///         PositionManager can open positions immediately after deploy.
///         Reads from contracts/.env:
///           INDEX_ORACLE_CONSUMER_ADDRESS (required)
///           ACTIVE_BASKETS (comma-separated, e.g. TOP20-JULY,TOP20-AUGUST)
///           BASKET_INITIAL_PRICES (comma-separated ints, same length;
///             defaults to 50 for each basket if unset)
///           ORACLE_SIGNER_PRIVATE_KEY (falls back to DEPLOYER_PRIVATE_KEY)
///         The Week-4 oracle-service will take over pushing live prices.
///         Usage:
///           forge script script/ConfigureBaskets.s.sol:ConfigureBaskets \
///             --rpc-url $RPC_URL --private-key $ORACLE_SIGNER_PRIVATE_KEY --broadcast
contract ConfigureBaskets is Script {
    function run() external {
        address consumer = vm.envAddress("INDEX_ORACLE_CONSUMER_ADDRESS");
        string[] memory basketNames = _split(vm.envString("ACTIVE_BASKETS"), ",");

        uint256[] memory prices = new uint256[](basketNames.length);
        if (
            !vm.envExists("BASKET_INITIAL_PRICES")
                || bytes(vm.envString("BASKET_INITIAL_PRICES")).length == 0
        ) {
            for (uint256 i = 0; i < prices.length; i++) {
                prices[i] = 50;
            }
        } else {
            string[] memory priceStrs = _split(vm.envString("BASKET_INITIAL_PRICES"), ",");
            require(priceStrs.length == basketNames.length, "prices/baskets length mismatch");
            for (uint256 i = 0; i < prices.length; i++) {
                prices[i] = vm.parseUint(priceStrs[i]);
            }
        }

        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        uint256 oracleKey = vm.envOr("ORACLE_SIGNER_PRIVATE_KEY", deployerKey);
        address signer = vm.addr(oracleKey);

        vm.startBroadcast(oracleKey);
        IndexOracleConsumer oracle = IndexOracleConsumer(consumer);
        for (uint256 i = 0; i < basketNames.length; i++) {
            bytes32 basketId = keccak256(abi.encodePacked(basketNames[i]));
            uint256 timestamp = block.timestamp;
            bytes memory sig = _signPriceUpdate(oracleKey, consumer, basketId, prices[i], timestamp);

            oracle.pushPrice(basketId, prices[i], timestamp, sig);
            console2.log(
                "seeded %s (%s) at price %s", basketNames[i], vm.toString(basketId), prices[i]
            );
        }
        vm.stopBroadcast();

        console2.log("oracle signer: %s", signer);
        console2.log("ConfigureBaskets: done for %s baskets", basketNames.length);
    }

    /// @dev Reads a private key from env, tolerating a missing 0x prefix.
    function _envPrivateKey(string memory name) internal returns (uint256) {
        string memory value = vm.envString(name);
        if (bytes(value).length >= 2 && bytes(value)[0] == "0" && bytes(value)[1] == "x") {
            return vm.parseUint(value);
        }
        return vm.parseUint(string.concat("0x", value));
    }

    function _signPriceUpdate(
        uint256 key,
        address consumer,
        bytes32 basketId,
        uint256 price,
        uint256 timestamp
    ) internal view returns (bytes memory) {
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
                block.chainid,
                consumer
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    function _split(string memory input, string memory delimiter)
        internal
        pure
        returns (string[] memory)
    {
        bytes memory del = bytes(delimiter);
        bytes memory buf = new bytes(0);
        uint256 parts = 1;
        for (uint256 i = 0; i < bytes(input).length; i++) {
            if (bytes(input)[i] == del[0]) parts++;
        }

        string[] memory result = new string[](parts);
        uint256 part = 0;
        for (uint256 i = 0; i < bytes(input).length + 1; i++) {
            bool atEnd = i == bytes(input).length;
            bool isDelim = !atEnd && bytes(input)[i] == del[0];
            if (atEnd || isDelim) {
                result[part] = string(buf);
                part++;
                buf = new bytes(0);
            } else {
                bytes memory tmp = new bytes(buf.length + 1);
                for (uint256 j = 0; j < buf.length; j++) {
                    tmp[j] = buf[j];
                }
                tmp[buf.length] = bytes(input)[i];
                buf = tmp;
            }
        }
        return result;
    }
}
