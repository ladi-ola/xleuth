// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {SettlementEngine} from "../src/SettlementEngine.sol";
import {PositionManager} from "../src/PositionManager.sol";

/// @title DeploySettlementEngine
/// @notice Deploys the SettlementEngine against the existing Week-5
///         PositionManager and authorizes it (owner-only setSettlementEngine).
///         Reuses the deployed vault/PM/oracle consumer — no redeploy.
///         The settlement signer defaults to the deployer key when
///         SETTLEMENT_SIGNER_PRIVATE_KEY is unset (MVP single-controlled-key).
///         Basket expiries are registered only when BASKET_EXPIRY_SECONDS != 0
///         (mirrors RedeployCore).
///         Reads from contracts/.env:
///           DEPLOYER_PRIVATE_KEY, POSITION_MANAGER_ADDRESS,
///           SETTLEMENT_SIGNER_PRIVATE_KEY (optional),
///           INDEX_PRICE_SCALE, SETTLEMENT_MAX_STALENESS_SECONDS,
///           ACTIVE_BASKETS, BASKET_EXPIRY_SECONDS (optional).
///         Usage:
///           forge script script/DeploySettlementEngine.s.sol:DeploySettlementEngine \
///             --rpc-url $RPC_URL --private-key $DEPLOYER_PRIVATE_KEY --broadcast
contract DeploySettlementEngine is Script {
    function run() external {
        revert("Legacy settlement deployment disabled: use reviewed atomic ledger");
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        address pmAddress = vm.envAddress("POSITION_MANAGER_ADDRESS");

        uint256 priceScale = vm.envOr("INDEX_PRICE_SCALE", uint256(100));
        uint256 settlementStaleness = vm.envOr("SETTLEMENT_MAX_STALENESS_SECONDS", uint256(3600));
        uint256 basketExpiry = vm.envOr("BASKET_EXPIRY_SECONDS", uint256(0));
        uint256 settlementKey = vm.envOr("SETTLEMENT_SIGNER_PRIVATE_KEY", deployerKey);

        vm.startBroadcast(deployerKey);

        SettlementEngine engine = new SettlementEngine(
            deployer,
            pmAddress,
            vm.addr(settlementKey),
            priceScale,
            settlementStaleness
        );
        console2.log("SettlementEngine deployed:", address(engine));

        PositionManager(pmAddress).setSettlementEngine(address(engine));
        console2.log("SettlementEngine authorized on PositionManager:", address(engine));

        if (basketExpiry != 0) {
            string[] memory basketNames = _split(vm.envString("ACTIVE_BASKETS"), ",");
            for (uint256 i = 0; i < basketNames.length; i++) {
                engine.setBasketExpiry(keccak256(bytes(basketNames[i])), basketExpiry);
            }
            console2.log("Registered %d basket expiries at %d", basketNames.length, basketExpiry);
        }

        vm.stopBroadcast();

        console2.log("---");
        console2.log("SETTLEMENT_ENGINE_ADDRESS=%s", address(engine));
    }

    function _split(string memory value, string memory delimiter)
        internal
        pure
        returns (string[] memory out)
    {
        uint256 count = 1;
        bytes memory v = bytes(value);
        bytes1 d = bytes(delimiter)[0];
        for (uint256 i = 0; i < v.length; i++) {
            if (v[i] == d) count++;
        }
        out = new string[](count);
        uint256 start = 0;
        uint256 idx = 0;
        for (uint256 i = 0; i < v.length; i++) {
            if (v[i] == d) {
                out[idx++] = _substring(value, start, i);
                start = i + 1;
            }
        }
        out[idx] = _substring(value, start, v.length);
        return out;
    }

    function _substring(string memory value, uint256 start, uint256 end)
        internal
        pure
        returns (string memory)
    {
        bytes memory v = bytes(value);
        bytes memory out = new bytes(end - start);
        for (uint256 i = start; i < end; i++) {
            out[i - start] = v[i];
        }
        return string(out);
    }

    /// @dev Reads a private key from env, tolerating a missing 0x prefix.
    function _envPrivateKey(string memory name) internal returns (uint256) {
        string memory value = vm.envString(name);
        if (bytes(value).length >= 2 && bytes(value)[0] == "0" && bytes(value)[1] == "x") {
            return vm.parseUint(value);
        }
        return vm.parseUint(string.concat("0x", value));
    }
}
