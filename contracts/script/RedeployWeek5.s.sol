// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {PositionManager} from "../src/PositionManager.sol";

/// @title RedeployWeek5
/// @notice Week-5 redeploy: fresh vault + PositionManager pair carrying the
///         `updatePosition` (open/increase/flatten) matching-engine entry
///         point. The vault and PositionManager are immutable-bound, so the
///         Week-4 vault can never gain the new functions — a full pair
///         redeploy is required. Reuses the deployed MockUSDC and
///         IndexOracleConsumer unchanged (the oracle signer and all pushed
///         prices remain valid). Existing testnet positions/deposits on the
///         superseded pair are lost — acceptable on Amoy.
///         Reads from contracts/.env:
///           DEPLOYER_PRIVATE_KEY, TEST_USDC_ADDRESS,
///           INDEX_ORACLE_CONSUMER_ADDRESS, MAX_LEVERAGE,
///           MAX_PRICE_STALENESS_SECONDS, MAINTENANCE_MARGIN_RATIO_BPS,
///           LIQUIDATION_FEE_BPS.
///         Usage:
///           forge script script/RedeployWeek5.s.sol:RedeployWeek5 \
///             --rpc-url $RPC_URL --private-key $DEPLOYER_PRIVATE_KEY --broadcast
contract RedeployWeek5 is Script {
    function run() external {
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        uint256 maxLeverage = vm.envOr("MAX_LEVERAGE", uint256(5));
        uint256 maxStaleness = vm.envOr("MAX_PRICE_STALENESS_SECONDS", uint256(60));
        uint256 maintenanceMarginRatioBps = vm.envOr("MAINTENANCE_MARGIN_RATIO_BPS", uint256(625));
        uint256 liquidationFeeBps = vm.envOr("LIQUIDATION_FEE_BPS", uint256(50));

        address usdc = vm.envAddress("TEST_USDC_ADDRESS");
        address oracleConsumer = vm.envAddress("INDEX_ORACLE_CONSUMER_ADDRESS");

        vm.startBroadcast(deployerKey);

        CollateralVault vault = new CollateralVault(usdc, deployer);
        console2.log("CollateralVault deployed:", address(vault));

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

        vault.setPositionManager(address(positionManager));
        console2.log("PositionManager authorized on vault:", address(positionManager));

        vm.stopBroadcast();

        console2.log("---");
        console2.log("COLLATERAL_VAULT_ADDRESS=%s", address(vault));
        console2.log("POSITION_MANAGER_ADDRESS=%s", address(positionManager));
        console2.log("INDEX_ORACLE_CONSUMER_ADDRESS=%s", oracleConsumer);
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
