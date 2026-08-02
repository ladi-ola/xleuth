// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @title MockUSDC
/// @notice Testnet-only USDC stand-in (6 decimals) with an open mint.
///         Used for local Foundry tests and as a fallback token when no
///         real Amoy test-USDC address is configured. Never deploy on mainnet.
contract MockUSDC is ERC20 {
    uint8 private constant _DECIMALS = 6;

    constructor(string memory name_, string memory symbol_) ERC20(name_, symbol_) {}

    function decimals() public pure override returns (uint8) {
        return _DECIMALS;
    }

    /// @notice Testnet faucet mint — no access control by design.
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
