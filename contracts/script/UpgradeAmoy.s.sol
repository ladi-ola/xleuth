// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {SettlementEngine} from "../src/SettlementEngine.sol";

/// @title UpgradeAmoy
/// @notice Gas-lean Week-4 upgrade for an already-deployed Amoy stack.
///         Reuses the deployed CollateralVault + IndexOracleConsumer
///         (authorized oracle signer stays as-is) and deploys a fresh
///         PositionManager (now with settlement/liquidation support) plus the
///         SettlementEngine, then re-points the vault and wires the PM.
///         Reads from contracts/.env:
///           DEPLOYER_PRIVATE_KEY, POSITION_MANAGER_ADDRESS (old, unused here),
///           COLLATERAL_VAULT_ADDRESS, INDEX_ORACLE_CONSUMER_ADDRESS,
///           TEST_USDC_ADDRESS (ignored, vault keeps its token),
///           MAX_LEVERAGE, MAX_PRICE_STALENESS_SECONDS,
///           INDEX_PRICE_SCALE, MAINTENANCE_MARGIN_RATIO_BPS,
///           LIQUIDATION_FEE_BPS, SETTLEMENT_SIGNER_PRIVATE_KEY (falls back to
///           the deployer key; must match the value DeployAmoy used),
///           SETTLEMENT_MAX_STALENESS_SECONDS, BASKET_EXPIRY_SECONDS
///           (0 = skip expiry registration).
///         Usage:
///           forge script script/UpgradeAmoy.s.sol:UpgradeAmoy \
///             --rpc-url $RPC_URL --private-key $DEPLOYER_PRIVATE_KEY --broadcast
contract UpgradeAmoy is Script {
    function run() external {
        revert("Legacy upgrade disabled: unsafe unilateral position accounting");
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        uint256 maxLeverage = vm.envOr("MAX_LEVERAGE", uint256(5));
        uint256 maxStaleness = vm.envOr("MAX_PRICE_STALENESS_SECONDS", uint256(60));
        uint256 priceScale = vm.envOr("INDEX_PRICE_SCALE", uint256(100));
        uint256 maintenanceMarginRatioBps = vm.envOr("MAINTENANCE_MARGIN_RATIO_BPS", uint256(625));
        uint256 liquidationFeeBps = vm.envOr("LIQUIDATION_FEE_BPS", uint256(50));
        uint256 settlementStaleness = vm.envOr("SETTLEMENT_MAX_STALENESS_SECONDS", uint256(3600));
        uint256 basketExpiry = vm.envOr("BASKET_EXPIRY_SECONDS", uint256(0));
        uint256 settlementKey = vm.envOr("SETTLEMENT_SIGNER_PRIVATE_KEY", deployerKey);

        CollateralVault vault = CollateralVault(vm.envAddress("COLLATERAL_VAULT_ADDRESS"));
        address oracleConsumer = vm.envAddress("INDEX_ORACLE_CONSUMER_ADDRESS");

        vm.startBroadcast(deployerKey);

        PositionManager positionManager = new PositionManager(
            deployer,
            address(vault),
            oracleConsumer,
            maxLeverage,
            maxStaleness,
            maintenanceMarginRatioBps,
            liquidationFeeBps
        );
        console2.log("PositionManager deployed:", address(positionManager));

        SettlementEngine settlementEngine = new SettlementEngine(
            deployer,
            address(positionManager),
            vm.addr(settlementKey),
            priceScale,
            settlementStaleness
        );
        console2.log("SettlementEngine deployed:", address(settlementEngine));

        vault.setPositionManager(address(positionManager));
        console2.log("Vault re-pointed to new PositionManager:", address(positionManager));

        positionManager.setSettlementEngine(address(settlementEngine));
        console2.log("SettlementEngine authorized on PositionManager:", address(settlementEngine));

        if (basketExpiry != 0) {
            string[] memory basketNames = _split(vm.envString("ACTIVE_BASKETS"), ",");
            for (uint256 i = 0; i < basketNames.length; i++) {
                settlementEngine.setBasketExpiry(keccak256(bytes(basketNames[i])), basketExpiry);
                console2.log("Expiry registered for %s: %s", basketNames[i], basketExpiry);
            }
        }

        vm.stopBroadcast();

        console2.log("---");
        console2.log("COLLATERAL_VAULT_ADDRESS=%s", address(vault));
        console2.log("POSITION_MANAGER_ADDRESS=%s", address(positionManager));
        console2.log("INDEX_ORACLE_CONSUMER_ADDRESS=%s", oracleConsumer);
        console2.log("SETTLEMENT_ENGINE_ADDRESS=%s", address(settlementEngine));
        console2.log("settlementSigner=%s", vm.addr(settlementKey));
        console2.log("maintenanceBps=%s", maintenanceMarginRatioBps);
        console2.log("liquidationFeeBps=%s", liquidationFeeBps);
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
