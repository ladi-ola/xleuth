// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IndexOracleConsumer} from "./IndexOracleConsumer.sol";
import {CollateralVault} from "./CollateralVault.sol";

/// @title PositionManager
/// @notice Opens and closes long/short positions on Xleuth baskets.
///         Margin = notional / leverage, where notional = size * index price
///         read from the IndexOracleConsumer. The oracle price must be fresh
///         (within maxStaleness of the last push). Leverage is capped by a
///         configurable, owner-settable parameter. Opening a position locks
///         margin in the CollateralVault; closing releases it back to the
///         user's free balance. Liquidation and settlement are out of scope
///         for this release (handled by SettlementEngine, next milestone).
///         One net position per user per basket_id; opposite-side opens on an
///         existing position are rejected (flattening is out of scope for v1).
contract PositionManager is Ownable {
    CollateralVault public immutable vault;
    IndexOracleConsumer public immutable oracle;

    /// @notice Maximum leverage any user may select (owner-settable).
    uint256 public maxLeverage;

    /// @notice Max age of the oracle price accepted for a trade (seconds).
    uint256 public maxStaleness;

    enum Side {
        Long,
        Short
    }

    struct Position {
        Side side;
        uint256 size;
        uint256 entryPrice;
        uint256 leverage;
        uint256 lockedMargin;
    }

    /// @notice Open position per user per basket_id.
    mapping(address user => mapping(bytes32 basketId => Position)) public positions;

    event PositionOpened(
        address indexed user,
        bytes32 indexed basketId,
        Side side,
        uint256 size,
        uint256 entryPrice,
        uint256 leverage,
        uint256 marginLocked
    );
    event PositionClosed(
        address indexed user,
        bytes32 indexed basketId,
        Side side,
        uint256 size,
        uint256 entryPrice,
        uint256 marginReleased
    );
    event MaxLeverageSet(address indexed caller, uint256 maxLeverage);
    event MaxStalenessSet(address indexed caller, uint256 maxStaleness);

    error ZeroAddress();
    error ZeroSize();
    error InvalidLeverage();
    error PriceNotFresh();
    error ZeroPrice();
    error PositionExists();
    error NoOpenPosition();
    error InvalidPrice();

    constructor(
        address owner_,
        address vault_,
        address oracle_,
        uint256 maxLeverage_,
        uint256 maxStaleness_
    ) Ownable(owner_) {
        if (vault_ == address(0) || oracle_ == address(0)) {
            revert ZeroAddress();
        }
        vault = CollateralVault(vault_);
        oracle = IndexOracleConsumer(oracle_);
        if (maxLeverage_ == 0) revert InvalidLeverage();
        maxLeverage = maxLeverage_;
        maxStaleness = maxStaleness_;
    }

    /// @notice Owner-only: change the leverage cap. Existing positions
    ///         keep their original leverage; the cap binds on new opens.
    function setMaxLeverage(uint256 maxLeverage_) external onlyOwner {
        if (maxLeverage_ == 0) revert InvalidLeverage();
        maxLeverage = maxLeverage_;
        emit MaxLeverageSet(msg.sender, maxLeverage_);
    }

    /// @notice Owner-only: change the oracle price staleness window.
    function setMaxStaleness(uint256 maxStaleness_) external onlyOwner {
        maxStaleness = maxStaleness_;
        emit MaxStalenessSet(msg.sender, maxStaleness_);
    }

    /// @notice Open a new position. Margin is locked in the vault immediately;
    ///         reverts if the user's free balance is insufficient (the vault
    ///         enforces the undercollateralization check).
    function openPosition(bytes32 basketId, Side side, uint256 size, uint256 leverage) external {
        if (size == 0) revert ZeroSize();
        if (leverage == 0 || leverage > maxLeverage) revert InvalidLeverage();

        Position storage pos = positions[msg.sender][basketId];
        if (pos.size != 0) revert PositionExists();

        (uint256 price, uint256 updatedAt) = oracle.priceOf(basketId);
        if (updatedAt == 0) revert PriceNotFresh();
        if (block.timestamp > updatedAt + maxStaleness) revert PriceNotFresh();
        if (price == 0) revert ZeroPrice();

        uint256 notional = price * size;
        uint256 margin = notional / leverage;
        if (margin == 0) revert InvalidPrice();

        vault.lockMargin(msg.sender, margin);

        positions[msg.sender][basketId] = Position({
            side: side, size: size, entryPrice: price, leverage: leverage, lockedMargin: margin
        });

        emit PositionOpened(msg.sender, basketId, side, size, price, leverage, margin);
    }

    /// @notice Close the user's position fully, releasing the locked margin
    ///         back to their free balance. PnL realization is handled by the
    ///         SettlementEngine milestone — this release just returns margin.
    function closePosition(bytes32 basketId) external {
        Position storage pos = positions[msg.sender][basketId];
        if (pos.size == 0) revert NoOpenPosition();

        uint256 margin = pos.lockedMargin;
        Side side = pos.side;
        uint256 size = pos.size;
        uint256 entryPrice = pos.entryPrice;

        delete positions[msg.sender][basketId];

        vault.releaseMargin(msg.sender, margin);

        emit PositionClosed(msg.sender, basketId, side, size, entryPrice, margin);
    }

    /// @notice Open position of a user on a basket (zero struct if none).
    function getPosition(address user, bytes32 basketId) external view returns (Position memory) {
        return positions[user][basketId];
    }
}
