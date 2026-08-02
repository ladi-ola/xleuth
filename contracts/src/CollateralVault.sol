// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title CollateralVault
/// @notice Custody contract for cash-settled dated index futures on Xleuth.
///         Holds all user collateral (test-USDC on Amoy) and tracks each
///         user's free vs. locked (margin) balance. Only the PositionManager
///         (the sole authorized operator) may lock/release margin; all other
///         balance movement is user-driven deposit/withdraw.
contract CollateralVault is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable collateralToken;

    /// @notice Only address that may call lockMargin/releaseMargin.
    address public positionManager;

    mapping(address user => uint256) public freeBalance;
    mapping(address user => uint256) public lockedBalance;

    event Deposit(address indexed user, uint256 amount);
    event Withdraw(address indexed user, uint256 amount);
    event MarginLocked(address indexed user, address indexed caller, uint256 amount);
    event MarginReleased(address indexed user, address indexed caller, uint256 amount);
    event PositionManagerSet(address indexed caller, address indexed positionManager);

    error NotPositionManager();
    error InsufficientFreeBalance();
    error InvalidAmount();
    error ZeroAddress();

    constructor(address collateralToken_, address initialOwner_) Ownable(initialOwner_) {
        if (collateralToken_ == address(0)) revert ZeroAddress();
        collateralToken = IERC20(collateralToken_);
    }

    /// @notice Admin-only: designate the PositionManager as the sole operator
    ///         allowed to lock/release margin. Callable repeatedly to migrate.
    function setPositionManager(address positionManager_) external onlyOwner {
        if (positionManager_ == address(0)) revert ZeroAddress();
        positionManager = positionManager_;
        emit PositionManagerSet(msg.sender, positionManager_);
    }

    /// @notice Pull `amount` of collateral from the user's wallet into the vault.
    function deposit(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        collateralToken.safeTransferFrom(msg.sender, address(this), amount);
        freeBalance[msg.sender] += amount;
        emit Deposit(msg.sender, amount);
    }

    /// @notice Send `amount` of free collateral back to the user.
    ///         Locked (margin) collateral can never be withdrawn directly.
    function withdraw(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidAmount();
        if (freeBalance[msg.sender] < amount) revert InsufficientFreeBalance();
        freeBalance[msg.sender] -= amount;
        collateralToken.safeTransfer(msg.sender, amount);
        emit Withdraw(msg.sender, amount);
    }

    /// @notice PositionManager-only: move free balance into locked margin.
    function lockMargin(address user, uint256 amount) external nonReentrant {
        if (msg.sender != positionManager) revert NotPositionManager();
        if (freeBalance[user] < amount) revert InsufficientFreeBalance();
        freeBalance[user] -= amount;
        lockedBalance[user] += amount;
        emit MarginLocked(user, msg.sender, amount);
    }

    /// @notice PositionManager-only: return margin to the user's free balance.
    function releaseMargin(address user, uint256 amount) external nonReentrant {
        if (msg.sender != positionManager) revert NotPositionManager();
        if (lockedBalance[user] < amount) revert InsufficientLockedBalance();
        lockedBalance[user] -= amount;
        freeBalance[user] += amount;
        emit MarginReleased(user, msg.sender, amount);
    }

    /// @notice Total collateral held by the vault (free + locked across all users).
    function totalCollateral() external view returns (uint256) {
        return collateralToken.balanceOf(address(this));
    }

    /// @notice Free + locked collateral of a single user.
    function balanceOf(address user) external view returns (uint256) {
        return freeBalance[user] + lockedBalance[user];
    }

    error InsufficientLockedBalance();
}
