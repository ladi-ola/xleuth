// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @title DeployAmoy
/// @notice Deploys the full Week-3 contract stack on Polygon Amoy.
///         Everything is read from contracts/.env — no hardcoded secrets:
///           RPC_URL, DEPLOYER_PRIVATE_KEY, MAX_LEVERAGE,
///           MAX_PRICE_STALENESS_SECONDS, TEST_USDC_ADDRESS,
///           ORACLE_SIGNER_PRIVATE_KEY (falls back to the deployer key),
///           INDEX_PRICE_SCALE (defaults to 100).
///         If TEST_USDC_ADDRESS is empty a fresh MockUSDC is deployed and
///         used (testnet dev flow only).
///         Usage:
///           forge script script/DeployAmoy.s.sol:DeployAmoy --rpc-url $RPC_URL \
///             --private-key $DEPLOYER_PRIVATE_KEY --broadcast --verify
contract DeployAmoy is Script {
    function run() external {
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        uint256 maxLeverage = vm.envOr("MAX_LEVERAGE", uint256(5));
        uint256 maxStaleness = vm.envOr("MAX_PRICE_STALENESS_SECONDS", uint256(60));
        uint256 priceScale = vm.envOr("INDEX_PRICE_SCALE", uint256(100));

        vm.startBroadcast(deployerKey);

        address usdc = address(0);
        if (
            !vm.envExists("TEST_USDC_ADDRESS")
                || bytes(vm.envString("TEST_USDC_ADDRESS")).length == 0
        ) {
            MockUSDC mock = new MockUSDC("Test USDC", "USDC");
            usdc = address(mock);
            console2.log("MockUSDC deployed (no TEST_USDC_ADDRESS configured):", usdc);
        } else {
            usdc = vm.envAddress("TEST_USDC_ADDRESS");
            console2.log("Using configured test-USDC:", usdc);
        }

        address deployer = vm.addr(deployerKey);

        CollateralVault vault = new CollateralVault(usdc, deployer);
        console2.log("CollateralVault deployed:", address(vault));

        uint256 oracleKey = vm.envOr("ORACLE_SIGNER_PRIVATE_KEY", deployerKey);
        address oracleSigner = vm.addr(oracleKey);

        IndexOracleConsumer oracleConsumer =
            new IndexOracleConsumer(deployer, oracleSigner, priceScale, maxStaleness);
        console2.log("IndexOracleConsumer deployed:", address(oracleConsumer));
        console2.log("Authorized oracle signer:", oracleSigner);

        PositionManager positionManager = new PositionManager(
            deployer, address(vault), address(oracleConsumer), maxLeverage, maxStaleness
        );
        console2.log("PositionManager deployed:", address(positionManager));

        vault.setPositionManager(address(positionManager));
        console2.log("PositionManager authorized on vault:", address(positionManager));

        vm.stopBroadcast();

        console2.log("---");
        console2.log("COLLATERAL_VAULT_ADDRESS=%s", address(vault));
        console2.log("POSITION_MANAGER_ADDRESS=%s", address(positionManager));
        console2.log("INDEX_ORACLE_CONSUMER_ADDRESS=%s", address(oracleConsumer));
        if (usdc != address(0)) console2.log("TEST_USDC_ADDRESS=%s", usdc);
        console2.log(
            "maxLeverage=%s maxStaleness=%s priceScale=%s", maxLeverage, maxStaleness, priceScale
        );
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
