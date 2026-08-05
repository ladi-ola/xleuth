// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {PositionManager} from "../src/PositionManager.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @title OpenPosition
/// @notice Opens a real margin position on Amoy for a demo user:
///         mints test-USDC (MockUSDC open mint), approves the vault,
///         deposits, then opens a long at the current oracle price.
///         Env: POSITION_MANAGER_ADDRESS, TEST_USDC_ADDRESS, BASKET_NAME,
///         TRADER_PRIVATE_KEY (falls back to DEPLOYER_PRIVATE_KEY),
///         SIZE (base units), LEVERAGE, DEPOSIT_AMOUNT (USDC 6-dp).
///         Usage:
///           forge script script/OpenPosition.s.sol:OpenPosition \
///             --rpc-url $RPC_URL --private-key $TRADER_PRIVATE_KEY --broadcast
contract OpenPosition is Script {
    function run() external {
        address pm = vm.envAddress("POSITION_MANAGER_ADDRESS");
        address usdc = vm.envAddress("TEST_USDC_ADDRESS");
        bytes32 basketId = keccak256(bytes(vm.envString("BASKET_NAME")));
        uint256 size = vm.envUint("SIZE");
        uint256 leverage = vm.envUint("LEVERAGE");
        uint256 depositAmount = vm.envUint("DEPOSIT_AMOUNT");
        uint256 key = vm.envOr("TRADER_PRIVATE_KEY", _envPrivateKey("DEPLOYER_PRIVATE_KEY"));        address trader = vm.addr(key);

        PositionManager positionManager = PositionManager(pm);
        MockUSDC usdcToken = MockUSDC(usdc);

        (uint256 price, uint256 updatedAt) = positionManager.oracle().priceOf(basketId);
        console2.log("oracle price=%s ts=%s", price, updatedAt);

        vm.startBroadcast(key);

        if (depositAmount != 0) {
            usdcToken.mint(trader, depositAmount);
            usdcToken.approve(address(positionManager.vault()), depositAmount);
            positionManager.vault().deposit(depositAmount);
            console2.log("deposited %s USDC", depositAmount);
        }

        positionManager.openPosition(basketId, PositionManager.Side.Long, size, leverage);
        console2.log("opened LONG %s @ %s x%s", size, price, leverage);

        vm.stopBroadcast();

        console2.log("trader=%s", trader);
        console2.log("free=%s locked=%s", usdcToken.balanceOf(trader), 0);
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