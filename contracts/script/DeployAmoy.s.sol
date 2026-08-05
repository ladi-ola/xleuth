// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {CollateralVault} from "../src/CollateralVault.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {SettlementEngine} from "../src/SettlementEngine.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @title DeployAmoy
/// @notice Deploys the full Week-3+4 contract stack on Polygon Amoy.
///         Everything is read from contracts/.env — no hardcoded secrets:
///           RPC_URL, DEPLOYER_PRIVATE_KEY, MAX_LEVERAGE,
///           MAX_PRICE_STALENESS_SECONDS, TEST_USDC_ADDRESS,
///           ORACLE_SIGNER_PRIVATE_KEY (falls back to the deployer key),
///           INDEX_PRICE_SCALE (defaults to 100),
///           MAINTENANCE_MARGIN_RATIO_BPS (defaults to 625),
///           LIQUIDATION_FEE_BPS (defaults to 50),
///           SETTLEMENT_SIGNER_PRIVATE_KEY (falls back to the deployer key),
///           SETTLEMENT_MAX_STALENESS_SECONDS (defaults to 3600),
///           BASKET_EXPIRY_SECONDS (defaults to 0 = not registered yet).
///         If TEST_USDC_ADDRESS is empty a fresh MockUSDC is deployed and
///         used (testnet dev flow only).
///         Usage:
///           forge script script/DeployAmoy.s.sol:DeployAmoy --rpc-url $RPC_URL \
///             --private-key $DEPLOYER_PRIVATE_KEY --broadcast --verify
contract DeployAmoy is Script {
    function run() external {
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");

        vm.startBroadcast(deployerKey);

        uint256 maxLeverage = vm.envOr("MAX_LEVERAGE", uint256(5));
        uint256 maxStaleness = vm.envOr("MAX_PRICE_STALENESS_SECONDS", uint256(60));
        uint256 priceScale = vm.envOr("INDEX_PRICE_SCALE", uint256(100));
        uint256 maintenanceMarginRatioBps = vm.envOr("MAINTENANCE_MARGIN_RATIO_BPS", uint256(625));
        uint256 liquidationFeeBps = vm.envOr("LIQUIDATION_FEE_BPS", uint256(50));
        uint256 settlementStaleness = vm.envOr("SETTLEMENT_MAX_STALENESS_SECONDS", uint256(3600));
        uint256 basketExpiry = vm.envOr("BASKET_EXPIRY_SECONDS", uint256(0));

        address usdc = _resolveUsdc();

        address deployer = vm.addr(deployerKey);

        CollateralVault vault = new CollateralVault(usdc, deployer);
        console2.log("CollateralVault deployed:", address(vault));

        address oracleConsumer = _deployOracle(deployerKey, priceScale, maxStaleness);

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

        address settlementEngine =
            _deploySettlement(deployerKey, address(positionManager), priceScale, settlementStaleness, basketExpiry);

        positionManager.setSettlementEngine(settlementEngine);
        console2.log("SettlementEngine authorized on PositionManager:", settlementEngine);

        vm.stopBroadcast();

        console2.log("---");
        console2.log("COLLATERAL_VAULT_ADDRESS=%s", address(vault));
        console2.log("POSITION_MANAGER_ADDRESS=%s", address(positionManager));
        console2.log("INDEX_ORACLE_CONSUMER_ADDRESS=%s", oracleConsumer);
        console2.log("SETTLEMENT_ENGINE_ADDRESS=%s", settlementEngine);
        if (usdc != address(0)) console2.log("TEST_USDC_ADDRESS=%s", usdc);
        console2.log("maxLeverage=%s", maxLeverage);
        console2.log("maxStaleness=%s", maxStaleness);
        console2.log("priceScale=%s", priceScale);
        console2.log("maintenanceBps=%s", maintenanceMarginRatioBps);
        console2.log("liquidationFeeBps=%s", liquidationFeeBps);
    }

    function _resolveUsdc() internal returns (address usdc) {
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
    }

    function _deployOracle(uint256 deployerKey, uint256 priceScale, uint256 maxStaleness)
        internal
        returns (address)
    {
        uint256 oracleKey = vm.envOr("ORACLE_SIGNER_PRIVATE_KEY", deployerKey);
        address oracleSigner = vm.addr(oracleKey);
        IndexOracleConsumer oracleConsumer =
            new IndexOracleConsumer(vm.addr(deployerKey), oracleSigner, priceScale, maxStaleness);
        console2.log("IndexOracleConsumer deployed:", address(oracleConsumer));
        console2.log("Authorized oracle signer:", oracleSigner);
        return address(oracleConsumer);
    }

    function _deploySettlement(
        uint256 deployerKey,
        address positionManager,
        uint256 priceScale,
        uint256 settlementStaleness,
        uint256 basketExpiry
    ) internal returns (address) {
        uint256 settlementKey = vm.envOr("SETTLEMENT_SIGNER_PRIVATE_KEY", deployerKey);
        address settlementSigner = vm.addr(settlementKey);
        SettlementEngine settlementEngine = new SettlementEngine(
            vm.addr(deployerKey),
            positionManager,
            settlementSigner,
            priceScale,
            settlementStaleness
        );
        console2.log("SettlementEngine deployed:", address(settlementEngine));
        console2.log("Settlement signer:", settlementSigner);

        if (basketExpiry != 0) {
            // ACTIVE_BASKETS must be literal dated names here (e.g. TOP20-JULY);
            // month templates are only expanded by the ingestion service.
            string[] memory basketNames = _split(vm.envString("ACTIVE_BASKETS"), ",");
            for (uint256 i = 0; i < basketNames.length; i++) {
                settlementEngine.setBasketExpiry(keccak256(bytes(basketNames[i])), basketExpiry);
                console2.log("Expiry registered for %s: %s", basketNames[i], basketExpiry);
            }
        }
        return address(settlementEngine);
    }

    /// @dev Simple comma-split (env strings are comma-separated).
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
