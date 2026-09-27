// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @title MintMockUSDCReserve
/// @notice Mints a reserve of MockUSDC to the operator wallet.
///         Run with the deployer key (owner of MockUSDC), NOT the operator key.
///         Usage:
///           forge script script/MintMockUSDCReserve.s.sol:MintMockUSDCReserve --rpc-url $RPC_URL \
///             --private-key $DEPLOYER_PRIVATE_KEY --broadcast
contract MintMockUSDCReserve is Script {
    function run() external {
        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        address mockUSDCAddr = vm.envAddress("MOCK_USDC_ADDRESS");
        address operatorWallet = vm.envAddress("OPERATOR_WALLET_ADDRESS");

        if (mockUSDCAddr == address(0)) {
            console2.log("Error: MOCK_USDC_ADDRESS not set in env");
            return;
        }
        if (operatorWallet == address(0)) {
            console2.log("Error: OPERATOR_WALLET_ADDRESS not set in env");
            return;
        }

        MockUSDC mockUSDC = MockUSDC(mockUSDCAddr);

        vm.startBroadcast(deployerKey);

        uint256 amount = 10_000_000 * 10**6; // 10M USDC with 6 decimals
        mockUSDC.mint(operatorWallet, amount);
        console2.log("Minted %s MockUSDC to operator wallet: %s", amount, operatorWallet);

        uint256 balance = mockUSDC.balanceOf(operatorWallet);
        console2.log("Operator wallet balance: %s", balance);

        vm.stopBroadcast();

        console2.log("---");
        console2.log("Mint complete. Operator wallet: %s", operatorWallet);
        console2.log("Balance: %s", balance);
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