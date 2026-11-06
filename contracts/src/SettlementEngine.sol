// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {PositionManager} from "./PositionManager.sol";

/// @title SettlementEngine
/// @notice Accepts a signed, realized volume-weighted YES fraction for a basket
///         at its expiry and settles every open position against it via
///         PositionManager.settleBasket. The realized-fraction value is
///         computed off-chain by the settlement service from data-ingestion's
///         event-deduped live volume (NOT per-market Gamma volume) and signed
///         here by a designated EIP-712 signer; any caller may relay it.
///         Settlement is strictly rejected before the basket's registered
///         expiry timestamp, and a basket settles at most once. Basket expiries
///         are configurable by the owner to match when its markets resolve.
///         Realized fraction is expressed in the same fixed-point scale as the
///         oracle prices (0-100 index points, INDEX_PRICE_SCALE).
contract SettlementEngine is Ownable, EIP712 {
    using ECDSA for bytes32;

    PositionManager public immutable positionManager;

    /// @notice Sole signer authorized to propose realized settlement values.
    address public authorizedSigner;

    /// @notice Index-price scale used for realized fractions, mirroring
    ///         IndexOracleConsumer.priceScale (default 100).
    uint256 public immutable priceScale;

    /// @notice Max age, in seconds, of a signed settlement message we accept.
    uint256 public maxSettlementStaleness;

    /// @notice Post-UTC expiry timestamp (inclusive) per basket id.
    mapping(bytes32 basketId => uint256 expiry) public expiryOf;

    /// @notice True once a basket has been settled. A basket settles once.
    mapping(bytes32 basketId => bool settled) public isSettled;

    string private constant _SETTLE_TYPE =
        "SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)";
    bytes32 private constant _SETTLE_TYPEHASH = keccak256(bytes(_SETTLE_TYPE));

    event BasketExpiryRegistered(
        bytes32 indexed basketId, uint256 expiry, address indexed caller
    );
    event AuthorizedSignerSet(address indexed caller, address indexed signer);
    event MaxSettlementStalenessSet(address indexed caller, uint256 maxStaleness);
    event BasketSettled(
        bytes32 indexed basketId,
        uint256 settledPrice,
        uint256 timestamp,
        address indexed signer,
        address indexed relayer
    );

    error ZeroAddress();
    error UnknownBasket();
    error BasketAlreadySettled();
    error NotExpired();
    error InvalidFraction();
    error UnauthorizedSigner();
    error StaleSignature();
    error ExpiryAlreadyRegistered();

    constructor(
        address initialOwner_,
        address positionManager_,
        address authorizedSigner_,
        uint256 priceScale_,
        uint256 maxSettlementStaleness_
    ) Ownable(initialOwner_) EIP712("Xleuth Settlement", "1") {
        if (positionManager_ == address(0)) revert ZeroAddress();
        if (authorizedSigner_ == address(0)) revert ZeroAddress();
        if (priceScale_ == 0) revert InvalidFraction();
        positionManager = PositionManager(positionManager_);
        authorizedSigner = authorizedSigner_;
        priceScale = priceScale_;
        maxSettlementStaleness = maxSettlementStaleness_;
    }

    /// @notice Admin-only: set a basket's settlement expiry (Unix seconds).
    function setBasketExpiry(bytes32 basketId, uint256 expiry) external onlyOwner {
        if (basketId == bytes32(0) || expiry == 0) revert UnknownBasket();
        if (expiryOf[basketId] != 0 || isSettled[basketId]) revert ExpiryAlreadyRegistered();
        expiryOf[basketId] = expiry;
        positionManager.registerBasketExpiry(basketId, expiry);
        emit BasketExpiryRegistered(basketId, expiry, msg.sender);
    }

    /// @notice Admin-only: rotate the authorized settlement signer.
    function setAuthorizedSigner(address signer_) external onlyOwner {
        if (signer_ == address(0)) revert ZeroAddress();
        authorizedSigner = signer_;
        emit AuthorizedSignerSet(msg.sender, signer_);
    }

    /// @notice Admin-only: adjust the signed-message staleness window.
    function setMaxSettlementStaleness(uint256 window_) external onlyOwner {
        maxSettlementStaleness = window_;
        emit MaxSettlementStalenessSet(msg.sender, window_);
    }

    /// @notice Settle a basket at a signed realized value `realizedPrice`
    ///         (same 0-priceScale scale as oracle prices). Anyone may relay the
    ///         signed message. Reverts if the basket is unknown, already
    ///         settled, not yet expired, the value is out of range, the message
    ///         is stale, or the signer is not authorized. Successfully settles
    ///         every open position on the basket and marks it settled.
    function settleBasket(
        bytes32 basketId,
        uint256 realizedPrice,
        uint256 timestamp,
        bytes calldata signature
    ) external {
        uint256 expiry = expiryOf[basketId];
        if (expiry == 0) revert UnknownBasket();
        if (isSettled[basketId]) revert BasketAlreadySettled();
        if (block.timestamp < expiry) revert NotExpired();
        if (realizedPrice == 0 || realizedPrice > priceScale) revert InvalidFraction();
        if (timestamp + maxSettlementStaleness < block.timestamp) revert StaleSignature();

        bytes32 digest =
            _hashTypedDataV4(keccak256(abi.encode(_SETTLE_TYPEHASH, basketId, realizedPrice, timestamp)));
        address signer = digest.recover(signature);
        if (signer != authorizedSigner) revert UnauthorizedSigner();

        isSettled[basketId] = true;
        positionManager.settleBasket(basketId, realizedPrice);

        emit BasketSettled(basketId, realizedPrice, timestamp, signer, msg.sender);
    }
}
