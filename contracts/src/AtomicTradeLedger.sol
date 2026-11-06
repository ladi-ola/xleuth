// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {IAtomicTradeLedger, SignedOrderExecutor} from "./SignedOrderExecutor.sol";
import {IndexOracleConsumer} from "./IndexOracleConsumer.sol";

/// @notice Isolated, fully funded matched-lot ledger. It NEVER uses the legacy
/// vault or PositionManager. The executor signs BOTH sides and atomically calls
/// this contract; no individual position write exists. Every lot reserves the
/// trader's maximum possible loss, independent of the selected leverage.
/// @dev Each position ID identifies a single matched lot in its basket.
/// A matched replacement may transfer one side, fully or partially; the
/// exiting side's realized payout comes from the incoming trader's reserve,
/// and the counterparty's reserve is repriced atomically. Open lots settle
/// at expiry in individually bounded batches; no legacy balances are migrated.
contract AtomicTradeLedger is IAtomicTradeLedger, Ownable, EIP712, ReentrancyGuard {
    using SafeERC20 for IERC20;
    using ECDSA for bytes32;

    uint256 public constant PRICE_SCALE = 1_000;
    uint256 public constant MAX_PRICE = 100 * PRICE_SCALE;
    bytes32 public constant PROTOCOL = keccak256("Xleuth Atomic Ledger v2");
    bytes32 private constant SETTLE_TYPEHASH =
        keccak256("SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)");

    IERC20 public immutable collateral;
    IndexOracleConsumer public immutable oracle;
    address public executor;
    address public settlementSigner;
    uint256 public immutable maxPriceAge;
    uint256 public immutable maxDeviation;
    uint256 public immutable maxSettlementAge;
    uint256 public immutable oracleScale;

    struct Lot {
        address buyer;
        address seller;
        uint256 size;
        uint256 entryPrice;
        uint256 buyerReserve;
        uint256 sellerReserve;
    }

    struct Replacement {
        uint256 id;
        address opponent;
        uint256 oldExitPart;
        uint256 oldOpponentPart;
        uint256 exitPayout;
        uint256 newOpponentReserve;
    }

    mapping(address => uint256) public freeBalance;
    mapping(address => uint256) public reservedBalance;
    mapping(bytes32 => uint256) public expiryOf;
    mapping(bytes32 => bool) public isSettled;
    mapping(bytes32 => bool) public settlementStarted;
    mapping(bytes32 => uint256) public settlementPrice;
    mapping(bytes32 => uint256) public settlementCursor;
    mapping(bytes32 => Lot[]) private lots;

    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event BasketRegistered(bytes32 indexed basketId, uint256 expiry);
    event ExecutorBound(address indexed executor);
    event LotOpened(bytes32 indexed basketId, uint256 indexed lotId, address buyer, address seller, uint256 size, uint256 price);
    event LotReplaced(bytes32 indexed basketId, uint256 indexed lotId, address exiting, address entering, uint256 size, uint256 price);
    event SettlementStarted(bytes32 indexed basketId, uint256 price);
    event SettlementProgress(bytes32 indexed basketId, uint256 cursor, bool complete);

    error Unauthorized();
    error InvalidConfiguration();
    error InvalidBasket();
    error InvalidPrice();
    error StalePrice();
    error InsufficientBalance();
    error UnsupportedIntent();
    error InvalidSettlement();
    error InvalidCollateral();

    constructor(
        address owner_, address token_, address oracle_,
        address settlementSigner_, uint256 priceAge_, uint256 deviation_, uint256 settlementAge_
    ) Ownable(owner_) EIP712("Xleuth Atomic Settlement", "1") {
        if (
            token_.code.length == 0 || oracle_.code.length == 0
                || settlementSigner_ == address(0) || priceAge_ == 0 || settlementAge_ == 0
                || deviation_ > MAX_PRICE
        ) revert InvalidConfiguration();
        collateral = IERC20(token_);
        if (IERC20Metadata(token_).decimals() != 6) revert InvalidConfiguration();
        oracle = IndexOracleConsumer(oracle_);
        settlementSigner = settlementSigner_;
        maxPriceAge = priceAge_;
        maxDeviation = deviation_;
        maxSettlementAge = settlementAge_;
        oracleScale = IndexOracleConsumer(oracle_).priceScale();
        if (oracleScale == 0 || MAX_PRICE % oracleScale != 0) revert InvalidConfiguration();
    }

    function executionProtocol() external pure override returns (bytes32) { return PROTOCOL; }

    /// @notice Set exactly once after deploying the executor against this
    /// ledger. The reverse deployment order is otherwise impossible.
    function bindExecutor(address executor_) external onlyOwner {
        if (executor != address(0) || executor_ == address(0) || executor_.code.length == 0) {
            revert InvalidConfiguration();
        }
        try SignedOrderExecutor(executor_).ledger() returns (IAtomicTradeLedger target) {
            if (address(target) != address(this)) revert InvalidConfiguration();
        } catch {
            revert InvalidConfiguration();
        }
        executor = executor_;
        emit ExecutorBound(executor_);
    }

    function deposit(uint256 amount) external nonReentrant {
        if (amount == 0) revert InvalidCollateral();
        uint256 beforeBalance = collateral.balanceOf(address(this));
        collateral.safeTransferFrom(msg.sender, address(this), amount);
        if (collateral.balanceOf(address(this)) - beforeBalance != amount) revert InvalidCollateral();
        freeBalance[msg.sender] += amount;
        emit Deposited(msg.sender, amount);
    }

    function withdraw(uint256 amount) external nonReentrant {
        if (amount == 0 || amount > freeBalance[msg.sender]) revert InsufficientBalance();
        freeBalance[msg.sender] -= amount;
        collateral.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    function registerBasket(bytes32 basketId, uint256 expiry) external onlyOwner {
        if (basketId == bytes32(0) || expiry <= block.timestamp || expiryOf[basketId] != 0) {
            revert InvalidBasket();
        }
        expiryOf[basketId] = expiry;
        emit BasketRegistered(basketId, expiry);
    }

    function setSettlementSigner(address signer) external onlyOwner {
        if (signer == address(0)) revert InvalidConfiguration();
        settlementSigner = signer;
    }

    function lotCount(bytes32 basketId) external view returns (uint256) { return lots[basketId].length; }
    function getLot(bytes32 basketId, uint256 index) external view returns (Lot memory) {
        return lots[basketId][index];
    }

    function executeMatchedTrade(
        bytes32 basketId, Leg calldata buy, Leg calldata sell, uint256 size, uint256 price
    ) external override nonReentrant {
        if (msg.sender != executor) revert Unauthorized();
        if (expiryOf[basketId] <= block.timestamp || expiryOf[basketId] == 0 || settlementStarted[basketId]) {
            revert InvalidBasket();
        }
        if (buy.trader == address(0) || sell.trader == address(0) || buy.trader == sell.trader
            || size == 0 || price == 0 || price > MAX_PRICE
            || buy.leverage == 0 || buy.leverage > 5 || sell.leverage == 0 || sell.leverage > 5
        ) revert InvalidConfiguration();
        if (buy.reduceOnly && sell.reduceOnly) revert UnsupportedIntent();

        (uint256 mark, uint256 updatedAt) = oracle.priceOf(basketId);
        if (updatedAt == 0 || updatedAt > block.timestamp
            || block.timestamp - updatedAt > maxPriceAge || mark == 0 || mark > oracleScale
        ) revert StalePrice();
        uint256 scaledMark = Math.mulDiv(mark, MAX_PRICE, oracleScale);
        uint256 delta = scaledMark > price ? scaledMark - price : price - scaledMark;
        if (delta > maxDeviation) revert InvalidPrice();

        if (sell.reduceOnly) {
            _checkOpeningIntent(buy, true, scaledMark);
            _checkClosingIntent(sell, false, scaledMark);
            _replaceLot(basketId, sell, buy, size, price, true);
            return;
        }
        if (buy.reduceOnly) {
            _checkOpeningIntent(sell, false, scaledMark);
            _checkClosingIntent(buy, true, scaledMark);
            _replaceLot(basketId, buy, sell, size, price, false);
            return;
        }
        if (buy.positionId != bytes32(0) || sell.positionId != bytes32(0)) revert UnsupportedIntent();
        _checkOpeningIntent(buy, true, scaledMark);
        _checkOpeningIntent(sell, false, scaledMark);

        // In micro-USDC: (micro-contracts * milli-points) / 1000.
        // One total worst-case payout per lot. Long reserves the cost of its
        // exposure, short reserves the rest; payout at settlement is exactly
        // partitioned between the two accounts (including at price zero).
        uint256 total = Math.mulDiv(size, MAX_PRICE, PRICE_SCALE);
        uint256 buyerReserve = Math.mulDiv(size, price, PRICE_SCALE);
        uint256 sellerReserve = total - buyerReserve;
        if (freeBalance[buy.trader] < buyerReserve || freeBalance[sell.trader] < sellerReserve) {
            revert InsufficientBalance();
        }
        freeBalance[buy.trader] -= buyerReserve;
        freeBalance[sell.trader] -= sellerReserve;
        reservedBalance[buy.trader] += buyerReserve;
        reservedBalance[sell.trader] += sellerReserve;
        lots[basketId].push(Lot(buy.trader, sell.trader, size, price, buyerReserve, sellerReserve));
        emit LotOpened(basketId, lots[basketId].length - 1, buy.trader, sell.trader, size, price);
    }

    /// @dev ABI-encoded (uint8 kind, uint256 triggerPrice, bytes32 ocoGroup,
    /// bytes32 positionId, bytes32 salt). The gateway binds its keccak hash
    /// to the signed orderId. kind: 0 limit, 1 market, 2 breakout stop.
    /// A stop cannot execute before the signed trigger at the live mark.
    function _checkOpeningIntent(Leg calldata leg, bool buySide, uint256 mark) internal pure {
        if (leg.intent.length != 160 || keccak256(leg.intent) != leg.orderId) {
            revert UnsupportedIntent();
        }
        (uint8 kind, uint256 trigger, bytes32 group, bytes32 position, bytes32 salt) =
            abi.decode(leg.intent, (uint8, uint256, bytes32, bytes32, bytes32));
        if (salt == bytes32(0) || group != bytes32(0) || position != bytes32(0)
            || kind > 2 || (kind != 2 && trigger != 0)
            || (kind != 0 && !leg.fillOrKill)
        ) revert UnsupportedIntent();
        if (kind == 2) {
            if (trigger == 0 || trigger > MAX_PRICE
                || (buySide && mark < trigger) || (!buySide && mark > trigger)
            ) revert UnsupportedIntent();
        }
    }

    function _checkClosingIntent(Leg calldata leg, bool buySide, uint256 mark) internal pure {
        if (leg.positionId == bytes32(0) || leg.intent.length != 160
            || keccak256(leg.intent) != leg.orderId) revert UnsupportedIntent();
        (uint8 kind, uint256 trigger, bytes32 group, bytes32 position, bytes32 salt) =
            abi.decode(leg.intent, (uint8, uint256, bytes32, bytes32, bytes32));
        if (salt == bytes32(0) || position != leg.positionId || kind == 2 || kind > 4
            || ((kind == 0 || kind == 1) && (trigger != 0 || group != bytes32(0)))
            || ((kind == 1 || kind == 3 || kind == 4) && !leg.fillOrKill)
        ) revert UnsupportedIntent();
        if (kind == 3 || kind == 4) {
            if (trigger == 0 || trigger > MAX_PRICE || group == bytes32(0)) revert UnsupportedIntent();
            // A buy closes a short; a sell closes a long.
            bool triggered = kind == 3
                ? (buySide ? mark >= trigger : mark <= trigger)
                : (buySide ? mark <= trigger : mark >= trigger);
            if (!triggered) revert UnsupportedIntent();
        }
    }

    function _replaceLot(
        bytes32 basketId, Leg calldata exiting, Leg calldata entering,
        uint256 size, uint256 price, bool closeLong
    ) internal {
        Replacement memory r;
        r.id = uint256(exiting.positionId);
        if (r.id == 0 || r.id > lots[basketId].length) revert UnsupportedIntent();
        Lot storage oldLot = lots[basketId][r.id - 1];
        if (size > oldLot.size || oldLot.size == 0) revert UnsupportedIntent();
        r.opponent = closeLong ? oldLot.seller : oldLot.buyer;
        if ((closeLong ? oldLot.buyer : oldLot.seller) != exiting.trader
            || entering.trader == r.opponent) revert UnsupportedIntent();

        (uint8 kind,,,,) = abi.decode(exiting.intent, (uint8, uint256, bytes32, bytes32, bytes32));
        if (kind >= 3 && size != oldLot.size) revert UnsupportedIntent(); // attached SL/TP full close only

        uint256 totalPart = Math.mulDiv(size, MAX_PRICE, PRICE_SCALE);
        r.oldExitPart = Math.mulDiv(
            closeLong ? oldLot.buyerReserve : oldLot.sellerReserve, size, oldLot.size
        );
        r.oldOpponentPart = totalPart - r.oldExitPart;
        r.exitPayout = Math.mulDiv(size, price, PRICE_SCALE);
        if (!closeLong) r.exitPayout = totalPart - r.exitPayout;
        r.newOpponentReserve = totalPart - r.exitPayout;
        if (freeBalance[entering.trader] < r.exitPayout) revert InsufficientBalance();

        freeBalance[entering.trader] -= r.exitPayout;
        freeBalance[exiting.trader] += r.exitPayout;
        reservedBalance[exiting.trader] -= r.oldExitPart;
        reservedBalance[r.opponent] =
            reservedBalance[r.opponent] - r.oldOpponentPart + r.newOpponentReserve;
        reservedBalance[entering.trader] += r.exitPayout;

        if (size == oldLot.size) {
            lots[basketId][r.id - 1] = Lot(
                closeLong ? entering.trader : r.opponent,
                closeLong ? r.opponent : entering.trader,
                size, price,
                closeLong ? r.exitPayout : r.newOpponentReserve,
                closeLong ? r.newOpponentReserve : r.exitPayout
            );
            emit LotReplaced(basketId, r.id - 1, exiting.trader, entering.trader, size, price);
        } else {
            oldLot.size -= size;
            if (closeLong) {
                oldLot.buyerReserve -= r.oldExitPart;
                oldLot.sellerReserve -= r.oldOpponentPart;
            } else {
                oldLot.sellerReserve -= r.oldExitPart;
                oldLot.buyerReserve -= r.oldOpponentPart;
            }
            lots[basketId].push(Lot(
                closeLong ? entering.trader : r.opponent,
                closeLong ? r.opponent : entering.trader,
                size, price,
                closeLong ? r.exitPayout : r.newOpponentReserve,
                closeLong ? r.newOpponentReserve : r.exitPayout
            ));
            emit LotReplaced(basketId, lots[basketId].length - 1, exiting.trader, entering.trader, size, price);
        }
    }

    /// @notice Freeze a signed, zero-inclusive final price. The signature
    /// binds this ledger and chain via EIP-712; future signatures are rejected.
    function startSettlement(
        bytes32 basketId, uint256 price, uint256 timestamp, bytes calldata signature
    ) external {
        uint256 expiry = expiryOf[basketId];
        if (expiry == 0 || block.timestamp < expiry || settlementStarted[basketId]
            || price > MAX_PRICE || timestamp < expiry || timestamp > block.timestamp
            || block.timestamp - timestamp > maxSettlementAge
        ) revert InvalidSettlement();
        bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(SETTLE_TYPEHASH, basketId, price, timestamp)));
        if (digest.recover(signature) != settlementSigner) revert Unauthorized();
        settlementStarted[basketId] = true;
        settlementPrice[basketId] = price;
        emit SettlementStarted(basketId, price);
        if (lots[basketId].length == 0) {
            isSettled[basketId] = true;
            emit SettlementProgress(basketId, 0, true);
        }
    }

    /// @notice Permissionless bounded progress; accounts can withdraw payouts
    /// only after their lot has been processed. No unbounded loop per call.
    function settleBatch(bytes32 basketId, uint256 maxLots) external nonReentrant {
        if (!settlementStarted[basketId] || isSettled[basketId] || maxLots == 0 || maxLots > 100) {
            revert InvalidSettlement();
        }
        uint256 cursor = settlementCursor[basketId];
        uint256 end = cursor + maxLots;
        if (end > lots[basketId].length) end = lots[basketId].length;
        uint256 price = settlementPrice[basketId];
        while (cursor < end) {
            Lot storage lot = lots[basketId][cursor];
            uint256 longPayout = Math.mulDiv(lot.size, price, PRICE_SCALE);
            uint256 total = lot.buyerReserve + lot.sellerReserve;
            reservedBalance[lot.buyer] -= lot.buyerReserve;
            reservedBalance[lot.seller] -= lot.sellerReserve;
            freeBalance[lot.buyer] += longPayout;
            freeBalance[lot.seller] += total - longPayout;
            ++cursor;
        }
        settlementCursor[basketId] = cursor;
        bool complete = cursor == lots[basketId].length;
        if (complete) isSettled[basketId] = true;
        emit SettlementProgress(basketId, cursor, complete);
    }
}
