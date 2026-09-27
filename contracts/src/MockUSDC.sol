// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title MockUSDC
/// @notice Testnet-only USDC stand-in (6 decimals) with owner-restricted mint.
///         Owner is the deployer key used for other contracts in this package.
///         Never deploy on mainnet.
contract MockUSDC is ERC20, Ownable {
    uint8 private constant _DECIMALS = 6;

    constructor(string memory name_, string memory symbol_) ERC20(name_, symbol_) Ownable(msg.sender) {}

    function decimals() public pure override returns (uint8) {
        return _DECIMALS;
    }

    /// @notice Testnet admin mint — restricted to contract owner (deployer key).
    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }
}
