// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @title DeployMockUSDC
/// @notice Deploys the MockUSDC contract on Polygon Amoy.
///         Owner is set to the deployer (DEPLOYER_PRIVATE_KEY).
///         Usage:
///           forge script script/DeployMockUSDC.s.sol:DeployMockUSDC --rpc-url $RPC_URL \
///             --private-key $DEPLOYER_PRIVATE_KEY --broadcast --verify
contract DeployMockUSDC is Script {
    function run() external {
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");

        vm.startBroadcast(deployerKey);

        MockUSDC mockUSDC = new MockUSDC("Test USD Coin", "USDC");
        console2.log("MockUSDC deployed:", address(mockUSDC));
        console2.log("MockUSDC owner:", mockUSDC.owner());

        vm.stopBroadcast();

        console2.log("---");
        console2.log("MOCK_USDC_ADDRESS=%s", address(mockUSDC));
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