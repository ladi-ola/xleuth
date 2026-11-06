// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {SignatureChecker} from "@openzeppelin/contracts/utils/cryptography/SignatureChecker.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

/// @notice Deliberately NOT implemented by the legacy PositionManager: its
///         unilateral writes and unfunded PnL accounting are not safe to relay.
///         A reviewed ledger must enforce lifecycle, fresh mark prices,
///         position-bound reduce-only/OCO rules and solvency for BOTH legs.
interface IAtomicTradeLedger {
    struct Leg {
        address trader;
        uint256 leverage;
        bytes32 orderId;
        bytes32 positionId;
        bool reduceOnly;
        bytes intent;
    }

    function executionProtocol() external pure returns (bytes32);

    function executeMatchedTrade(
        bytes32 basketId,
        Leg calldata buy,
        Leg calldata sell,
        uint256 size,
        uint256 executionPrice
    ) external;
}

/// @title SignedOrderExecutor
/// @notice Trader-authorized, replay-protected, atomic matched-execution gateway.
///         Prices use 3 decimals, sizes/USDC 6. Neither trader keys nor AA are
///         required by the relayer. EOA and ERC-1271 signatures are supported.
/// @dev This gateway cannot be connected to the unsafe legacy PositionManager.
///      The financial ledger is a separate, REQUIRED implementation. It remains
///      blocked until the owner decides price-gap/shortfall handling. Deploying
///      this gateway alone does not enable trading or fix legacy balances.
contract SignedOrderExecutor is EIP712, ReentrancyGuard {
    uint256 public constant PRICE_SCALE = 1_000;
    uint256 public constant SIZE_SCALE = 1_000_000;
    uint256 public constant MAX_PRICE = 100 * PRICE_SCALE;
    uint256 public constant MIN_NOTIONAL = 10 * 1_000_000;
    uint256 public constant MAX_NOTIONAL = 1_000 * 1_000_000;
    bytes32 public constant EXECUTION_PROTOCOL = keccak256("Xleuth Atomic Ledger v2");

    // orderId binds the complete normalized API intent (including order type,
    // trigger/slippage/OCO fields). The ledger must validate those semantics;
    // this gateway enforces the signed execution envelope, not off-chain book
    // priority or an invented oracle/trigger policy.
    struct Authorization {
        address trader;
        bytes32 basketId;
        bytes32 orderId;
        uint8 side; // 0 = buy, 1 = sell
        uint256 size;
        uint256 maxNotional;
        uint256 minPrice;
        uint256 maxPrice;
        uint256 leverage;
        uint256 nonce;
        uint256 deadline;
        bool fillOrKill;
        bool reduceOnly;
        bytes32 positionId;
    }

    struct Match {
        Authorization buy;
        bytes buySignature;
        Authorization sell;
        bytes sellSignature;
        uint256 size;
        uint256 price;
        bytes buyIntent;
        bytes sellIntent;
    }

    bytes32 public constant AUTHORIZATION_TYPEHASH = keccak256(
        "Authorization(address trader,bytes32 basketId,bytes32 orderId,uint8 side,uint256 size,uint256 maxNotional,uint256 minPrice,uint256 maxPrice,uint256 leverage,uint256 nonce,uint256 deadline,bool fillOrKill,bool reduceOnly,bytes32 positionId)"
    );

    IAtomicTradeLedger public immutable ledger;
    address public immutable relayer;

    mapping(bytes32 digest => uint256) public filledSize;
    mapping(bytes32 digest => uint256) public filledNotional;
    mapping(address trader => mapping(uint256 nonce => bytes32)) public nonceDigest;
    mapping(address trader => mapping(uint256 nonce => bool)) public cancelledNonce;
    mapping(address trader => uint256) public minimumNonce;

    event NonceCancelled(address indexed trader, uint256 indexed nonce);
    event MinimumNonceRaised(address indexed trader, uint256 minimum);
    event MatchExecuted(
        bytes32 indexed buyDigest,
        bytes32 indexed sellDigest,
        bytes32 indexed basketId,
        uint256 size,
        uint256 price,
        uint256 notional
    );

    error InvalidLedger();
    error InvalidRelayer();
    error InvalidAuthorization();
    error InvalidSignature();
    error AuthorizationExpired();
    error AuthorizationCancelled();
    error NonceAlreadyBound();
    error InvalidMatch();
    error PriceOutsideAuthorization();
    error SizeExceeded();
    error NotionalExceeded();
    error NotionalBelowMinimum();
    error FillOrKillRequired();
    error IntentMismatch();

    constructor(address ledger_, address relayer_) EIP712("Xleuth Orders", "2") {
        if (ledger_.code.length == 0) revert InvalidLedger();
        if (relayer_ == address(0)) revert InvalidRelayer();
        // Refuse legacy PM addresses rather than assuming that an arbitrary
        // contract has the required atomic, restricted financial write path.
        try IAtomicTradeLedger(ledger_).executionProtocol() returns (bytes32 protocol) {
            if (protocol != EXECUTION_PROTOCOL) revert InvalidLedger();
        } catch {
            revert InvalidLedger();
        }
        ledger = IAtomicTradeLedger(ledger_);
        relayer = relayer_;
    }

    function hashAuthorization(Authorization calldata authorization) public view returns (bytes32) {
        // All tuple members are static ABI types: this encoding is identical
        // to the flattened EIP-712 struct encoding. Cross-language tests bind it.
        return _hashTypedDataV4(keccak256(abi.encode(AUTHORIZATION_TYPEHASH, authorization)));
    }

    function validateAuthorization(Authorization calldata authorization, bytes calldata signature)
        external
        view
        returns (bytes32 digest)
    {
        return _validate(authorization, signature);
    }

    /// @notice On-chain cancellation is authoritative even if an old copy of a
    ///         signature remains in a relayer/book. A wallet may batch calls.
    function cancelNonce(uint256 nonce) external {
        cancelledNonce[msg.sender][nonce] = true;
        emit NonceCancelled(msg.sender, nonce);
    }

    function raiseMinimumNonce(uint256 minimum) external {
        if (minimum <= minimumNonce[msg.sender]) revert InvalidAuthorization();
        minimumNonce[msg.sender] = minimum;
        emit MinimumNonceRaised(msg.sender, minimum);
    }

    /// @notice Exactly ONE ledger call for both sides. Any signature, limit or
    ///         ledger failure rolls back both fills and both nonce bindings.
    function executeMatch(Match calldata matched) external nonReentrant {
        if (msg.sender != relayer) revert InvalidRelayer();
        _executeMatch(matched);
        _checkFillOrKill(matched.buy);
        _checkFillOrKill(matched.sell);
    }

    /// @notice A market FOK may consume several makers. Every ledger update and
    ///         every signed order's fill accounting revert if ANY leg fails or
    ///         a FOK intent is incomplete at the end of this transaction.
    function executeMatches(Match[] calldata matches) external nonReentrant {
        if (msg.sender != relayer) revert InvalidRelayer();
        if (matches.length == 0) revert InvalidMatch();
        for (uint256 i; i < matches.length; ++i) {
            _executeMatch(matches[i]);
        }
        for (uint256 i; i < matches.length; ++i) {
            _checkFillOrKill(matches[i].buy);
            _checkFillOrKill(matches[i].sell);
        }
    }

    function _executeMatch(Match calldata matched) internal {
        Authorization calldata buy = matched.buy;
        Authorization calldata sell = matched.sell;
        uint256 size = matched.size;
        uint256 price = matched.price;
        if (
            buy.side != 0 || sell.side != 1 || buy.trader == sell.trader
                || buy.basketId != sell.basketId || buy.orderId == sell.orderId || size == 0
                || price == 0 || price > MAX_PRICE
        ) revert InvalidMatch();

        if (
            keccak256(matched.buyIntent) != buy.orderId
                || keccak256(matched.sellIntent) != sell.orderId
        ) {
            revert IntentMismatch();
        }

        bytes32 buyDigest = _validate(buy, matched.buySignature);
        bytes32 sellDigest = _validate(sell, matched.sellSignature);
        // Rounding up to a collateral base unit is conservative for the
        // signed spend ceiling; contract count itself is never rounded/skipped.
        uint256 notional = Math.mulDiv(size, price, PRICE_SCALE, Math.Rounding.Ceil);
        _consume(buy, buyDigest, size, price, notional);
        _consume(sell, sellDigest, size, price, notional);

        ledger.executeMatchedTrade(
            buy.basketId, _leg(buy, matched.buyIntent), _leg(sell, matched.sellIntent), size, price
        );
        emit MatchExecuted(buyDigest, sellDigest, buy.basketId, size, price, notional);
    }

    function _validate(Authorization calldata a, bytes calldata signature)
        internal
        view
        returns (bytes32 digest)
    {
        if (
            a.trader == address(0) || a.basketId == bytes32(0) || a.orderId == bytes32(0)
                || a.side > 1 || a.size == 0 || a.maxNotional < MIN_NOTIONAL
                || a.maxNotional > MAX_NOTIONAL || a.minPrice == 0 || a.minPrice > a.maxPrice
                || a.maxPrice > MAX_PRICE || a.leverage == 0 || a.leverage > 5
                || (a.reduceOnly && a.positionId == bytes32(0))
        ) revert InvalidAuthorization();
        if (block.timestamp > a.deadline) revert AuthorizationExpired();
        if (cancelledNonce[a.trader][a.nonce] || a.nonce < minimumNonce[a.trader]) {
            revert AuthorizationCancelled();
        }
        digest = hashAuthorization(a);
        bytes32 bound = nonceDigest[a.trader][a.nonce];
        if (bound != bytes32(0) && bound != digest) revert NonceAlreadyBound();
        // Recheck ERC-1271 on every fill: contract signatures may be revoked.
        if (!SignatureChecker.isValidSignatureNow(a.trader, digest, signature)) {
            revert InvalidSignature();
        }
    }

    function _consume(
        Authorization calldata a,
        bytes32 digest,
        uint256 size,
        uint256 price,
        uint256 notional
    ) internal {
        if (price < a.minPrice || price > a.maxPrice) {
            revert PriceOutsideAuthorization();
        }
        uint256 previousSize = filledSize[digest];
        if (size > a.size - previousSize) revert SizeExceeded();
        // The minimum is per authorized order, not per partial execution.
        // A $10 limit order may legitimately fill in smaller fragments.
        if (Math.mulDiv(a.size, price, PRICE_SCALE) < MIN_NOTIONAL) {
            revert NotionalBelowMinimum();
        }
        uint256 previousNotional = filledNotional[digest];
        if (notional > a.maxNotional - previousNotional) revert NotionalExceeded();
        nonceDigest[a.trader][a.nonce] = digest;
        filledSize[digest] = previousSize + size;
        filledNotional[digest] = previousNotional + notional;
    }

    function _checkFillOrKill(Authorization calldata a) internal view {
        if (a.fillOrKill && filledSize[hashAuthorization(a)] != a.size) {
            revert FillOrKillRequired();
        }
    }

    function _leg(Authorization calldata a, bytes calldata intent)
        internal
        pure
        returns (IAtomicTradeLedger.Leg memory)
    {
        return IAtomicTradeLedger.Leg(
            a.trader, a.leverage, a.orderId, a.positionId, a.reduceOnly, intent
        );
    }
}
