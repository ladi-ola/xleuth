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

    /// @notice Liquidation threshold, expressed in basis points (1/10000).
    ///         A position is liquidatable when its margin ratio
    ///         (      equity / notional, per the latest oracle price) is
    ///         strictly below this value. Boundary (ratio == threshold) is
    ///         NOT liquidatable.
    uint256 public maintenanceMarginRatioBps;

    /// @notice Reward to the liquidator, in basis points of the position's
    ///         notional value at liquidation, taken from the liquidated
    ///         position's margin (see CollateralVault.liquidatePosition).
    uint256 public liquidationFeeBps;

    /// @notice Address allowed to trigger basket settlement
    ///         (the SettlementEngine). Owner-settable.
    address public settlementEngine;

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

    /// @notice Users with an open position on a basket (one entry per user, since
    ///         a user can hold at most one net position per basket). Drives
    ///         liquidation-aware settlement enumeration.
    mapping(bytes32 basketId => address[]) public openUsers;

    /// @notice Index of a user within openUsers[basketId], for O(1) swap-remove.
    mapping(bytes32 basketId => mapping(address user => uint256)) internal openUserIndex;

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
    event PositionSettled(
        address indexed user,
        bytes32 indexed basketId,
        uint256 settlementPrice,
        int256 pnl,
        uint256 creditedBack
    );
    event PositionLiquidated(
        address indexed liquidator,
        address indexed user,
        bytes32 indexed basketId,
        uint256 size,
        uint256 liquidationPrice,
        uint256 liquidatorReward
    );
    event MaxLeverageSet(address indexed caller, uint256 maxLeverage);
    event MaxStalenessSet(address indexed caller, uint256 maxStaleness);
    event MaintenanceMarginRatioSet(address indexed caller, uint256 ratioBps);
    event LiquidationFeeSet(address indexed caller, uint256 feeBps);
    event SettlementEngineSet(address indexed caller, address indexed settlementEngine);

    error ZeroAddress();
    error ZeroSize();
    error InvalidLeverage();
    error PriceNotFresh();
    error ZeroPrice();
    error PositionExists();
    error NoOpenPosition();
    error InvalidPrice();
    error NotSettlementEngine();
    error NotLiquidatable();
    error ZeroMaintenanceMargin();
    error FeeExceedsNotional();

    constructor(
        address owner_,
        address vault_,
        address oracle_,
        uint256 maxLeverage_,
        uint256 maxStaleness_,
        uint256 maintenanceMarginRatioBps_,
        uint256 liquidationFeeBps_
    ) Ownable(owner_) {
        if (vault_ == address(0) || oracle_ == address(0)) {
            revert ZeroAddress();
        }
        vault = CollateralVault(vault_);
        oracle = IndexOracleConsumer(oracle_);
        if (maxLeverage_ == 0) revert InvalidLeverage();
        maxLeverage = maxLeverage_;
        maxStaleness = maxStaleness_;
        if (maintenanceMarginRatioBps_ == 0) revert ZeroMaintenanceMargin();
        maintenanceMarginRatioBps = maintenanceMarginRatioBps_;
        liquidationFeeBps = liquidationFeeBps_;
        settlementEngine = address(0);
    }

    /// @notice Owner-only: change the leverage cap. Existing positions
    ///         keep their original leverage; new opens bind.
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

    /// @notice Owner-only: set the maintenance margin threshold (basis points).
    function setMaintenanceMarginRatio(uint256 ratioBps) external onlyOwner {
        if (ratioBps == 0) revert ZeroMaintenanceMargin();
        maintenanceMarginRatioBps = ratioBps;
        emit MaintenanceMarginRatioSet(msg.sender, ratioBps);
    }

    /// @notice Owner-only: set the liquidator reward (basis points).
    function setLiquidationFee(uint256 feeBps) external onlyOwner {
        liquidationFeeBps = feeBps;
        emit LiquidationFeeSet(msg.sender, feeBps);
    }

    /// @notice Owner-only: designate the SettlementEngine authorized to settle
    ///         baskets.
    function setSettlementEngine(address settlementEngine_) external onlyOwner {
        if (settlementEngine_ == address(0)) revert ZeroAddress();
        settlementEngine = settlementEngine_;
        emit SettlementEngineSet(msg.sender, settlementEngine_);
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

        openUsers[basketId].push(msg.sender);
        openUserIndex[basketId][msg.sender] = openUsers[basketId].length - 1;

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

        _removeOpenUser(basketId, msg.sender);

        vault.releaseMargin(msg.sender, margin);

        emit PositionClosed(msg.sender, basketId, side, size, entryPrice, margin);
    }

    /// @notice Open position of a user on a basket (zero struct if none).
    function getPosition(address user, bytes32 basketId) external view returns (Position memory) {
        return positions[user][basketId];
    }

    /// @notice Users currently holding any position on a basket.
    function getOpenUserAt(bytes32 basketId, uint256 index) external view returns (address) {
        return openUsers[basketId][index];
    }

    function getOpenUserCount(bytes32 basketId) external view returns (uint256) {
        return openUsers[basketId].length;
    }

    // ── Liquidation ──────────────────────────────────────────────────────

    /// @notice Liquidate any user's position whose current margin ratio
    ///         (equity / notional at the latest live oracle price) is strictly
    ///         below maintenanceMarginRatioBps. Any caller may trigger; the
    ///         caller is rewarded liquidationFeeBps of the position's notional,
    ///         taken from the position's equity inside the CollateralVault.
    function liquidate(address user, bytes32 basketId) external {
        Position storage pos = positions[user][basketId];
        if (pos.size == 0) revert NoOpenPosition();

        uint256 price = _requireFreshPrice(basketId);
        uint256 notional = price * pos.size;
        int256 pnl = _pnl(pos, price);
        uint256 equity = _equity(pos.lockedMargin, pnl);

        // ratio (bps) = equity * 1e4 / notional; liquidatable strictly below.
        if (equity * 1e4 >= notional * maintenanceMarginRatioBps) revert NotLiquidatable();

        uint256 reward = (notional * liquidationFeeBps) / 1e4;
        uint256 lockedMargin = pos.lockedMargin;
        Side side = pos.side;
        uint256 size = pos.size;
        uint256 entryPrice = pos.entryPrice;

        delete positions[user][basketId];
        _removeOpenUser(basketId, user);

        vault.liquidatePosition(user, msg.sender, lockedMargin, pnl, reward);

        emit PositionLiquidated(msg.sender, user, basketId, size, price, reward);
        emit PositionClosed(user, basketId, side, size, entryPrice, lockedMargin);
    }

    // ── Expiry settlement (SettlementEngine-invoked) ─────────────────────

    /// @notice Settle EVERY open position on a basket at a realized index
    ///         value `settleValue` (same 0–100 scale as oracle prices). Only
    ///         the authorized SettlementEngine may call this, and it must be
    ///         after the basket's actual expiry (enforced on-chain in the
    ///         engine, which checks `block.timestamp >= expiry`). Each
    ///         position is closed against the realized value, the vault crediting
    ///         / debiting free balance accordingly (losses floored at zero).
    function settleBasket(bytes32 basketId, uint256 settleValue) external {
        if (msg.sender != settlementEngine) revert NotSettlementEngine();

        if (settleValue == 0) revert ZeroPrice();

        address[] storage users = openUsers[basketId];
        while (users.length > 0) {
            address user = users[users.length - 1];
            Position storage pos = positions[user][basketId];
            if (pos.size == 0) {
                _removeOpenUser(basketId, user);
                continue;
            }

            int256 pnl = _pnl(pos, settleValue);
            uint256 locked = pos.lockedMargin;
            Side side = pos.side;
            uint256 size = pos.size;
            uint256 entryPrice = pos.entryPrice;
            uint256 creditedBack = _pnl(pos, settleValue) < 0 ? _equity(locked, pnl) : locked + uint256(pnl);

            delete positions[user][basketId];
            _removeOpenUser(basketId, user);

            vault.settlePosition(user, locked, pnl);

            emit PositionSettled(user, basketId, settleValue, pnl, creditedBack);
            emit PositionClosed(user, basketId, side, size, entryPrice, locked);
        }
    }

    /// @notice Equity of an open position at the latest oracle price.
    function equityOf(address user, bytes32 basketId) external view returns (uint256) {
        Position storage pos = positions[user][basketId];
        if (pos.size == 0) return 0;
        (uint256 price,) = oracle.priceOf(basketId);
        return _equity(pos.lockedMargin, _pnl(pos, price));
    }

    function _requireFreshPrice(bytes32 basketId) internal view returns (uint256 price) {
        (uint256 p, uint256 updatedAt) = oracle.priceOf(basketId);
        if (updatedAt == 0) revert PriceNotFresh();
        if (block.timestamp > updatedAt + maxStaleness) revert PriceNotFresh();
        if (p == 0) revert ZeroPrice();
        return p;
    }

    function _equity(uint256 lockedMargin, int256 pnl) internal pure returns (uint256) {
        if (pnl < 0) {
            uint256 loss = uint256(-pnl);
            return loss > lockedMargin ? 0 : lockedMargin - loss;
        }
        return lockedMargin + uint256(pnl);
    }

    /// @notice Swap/remove a user from the per-basket open-user list.
    function _removeOpenUser(bytes32 basketId, address user) internal {
        uint256 index = openUserIndex[basketId][user];
        address[] storage users = openUsers[basketId];
        uint256 lastIndex = users.length - 1;
        if (index != lastIndex) {
            users[index] = users[lastIndex];
            openUserIndex[basketId][users[index]] = index;
        }
        users.pop();
        delete openUserIndex[basketId][user];
    }

    function _removeOpenPosition(bytes32 basketId, address user) internal {
        delete positions[user][basketId];
        _removeOpenUser(basketId, user);
    }

    /// @notice Directional realized PnL of a position at `price`:
    ///         (price - entry) * size for longs, (entry - price) * size for shorts.
    function _pnl(Position storage pos, uint256 price) internal view returns (int256) {
        int256 delta = int256(price) - int256(pos.entryPrice);
        int256 pnl = delta * int256(pos.size);
        if (pos.side == Side.Short) pnl = -pnl;
        return pnl;
    }
}
