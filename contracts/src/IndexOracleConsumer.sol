// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";

/// @title IndexOracleConsumer
/// @notice Consumes signed index price updates for Xleuth baskets.
///         MVP uses a single authorized signer (the oracle-service key from
///         Week 4) — there is no decentralized oracle network. Each update is
///         an EIP-712 signed message (basketId, price, timestamp); the contract
///         verifies the recovered signer and rejects stale or out-of-order
///         updates. Prices are scaled 0-100 index points (INDEX_PRICE_SCALE).
contract IndexOracleConsumer is Ownable, EIP712 {
    using ECDSA for bytes32;

    uint256 public immutable priceScale;

    /// @notice Sole authorized signer of price updates.
    address public authorizedOracle;

    /// @notice Maximum accepted age of an update's timestamp (seconds).
    uint256 public maxStaleness;

    struct PriceInfo {
        uint256 price;
        uint256 timestamp;
    }

    /// @notice Latest accepted price per basket_id.
    mapping(bytes32 basketId => PriceInfo) public latestPrice;

    string private constant _PRICE_TYPE =
        "PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)";
    bytes32 private constant _PRICE_TYPEHASH = keccak256(abi.encodePacked(_PRICE_TYPE));

    event PriceUpdated(
        bytes32 indexed basketId, uint256 price, uint256 timestamp, address indexed signer
    );
    event AuthorizedOracleSet(address indexed caller, address indexed oracle);
    event MaxStalenessSet(address indexed caller, uint256 maxStaleness);

    error ZeroAddress();
    error UnauthorizedSigner();
    error StaleUpdate();
    error PriceOutOfRange();

    constructor(
        address initialOwner_,
        address authorizedOracle_,
        uint256 priceScale_,
        uint256 maxStaleness_
    ) Ownable(initialOwner_) EIP712("Xleuth Index Oracle", "1") {
        if (authorizedOracle_ == address(0)) revert ZeroAddress();
        if (priceScale_ == 0) revert PriceOutOfRange();
        authorizedOracle = authorizedOracle_;
        priceScale = priceScale_;
        maxStaleness = maxStaleness_;
    }

    /// @notice Admin-only: rotate the authorized oracle signer.
    function setAuthorizedOracle(address oracle_) external onlyOwner {
        if (oracle_ == address(0)) revert ZeroAddress();
        authorizedOracle = oracle_;
        emit AuthorizedOracleSet(msg.sender, oracle_);
    }

    /// @notice Admin-only: adjust the staleness window.
    function setMaxStaleness(uint256 maxStaleness_) external onlyOwner {
        maxStaleness = maxStaleness_;
        emit MaxStalenessSet(msg.sender, maxStaleness_);
    }

    /// @notice Push a signed price update for a basket.
    ///         Reverts if: signer is not authorized, the update is older than
    ///         the maxStaleness window, out of order vs. the last accepted
    ///         update, or the price is outside (0, priceScale].
    function pushPrice(bytes32 basketId, uint256 price, uint256 timestamp, bytes calldata signature)
        external
    {
        PriceInfo memory last = latestPrice[basketId];

        if (timestamp <= last.timestamp) revert StaleUpdate();
        if (timestamp + maxStaleness < block.timestamp) revert StaleUpdate();
        if (price == 0 || price > priceScale) revert PriceOutOfRange();

        bytes32 digest =
            _hashTypedDataV4(keccak256(abi.encode(_PRICE_TYPEHASH, basketId, price, timestamp)));
        address signer = digest.recover(signature);
        if (signer != authorizedOracle) revert UnauthorizedSigner();

        latestPrice[basketId] = PriceInfo({price: price, timestamp: timestamp});
        emit PriceUpdated(basketId, price, timestamp, signer);
    }

    /// @notice Latest price and update timestamp for a basket.
    function priceOf(bytes32 basketId) external view returns (uint256 price, uint256 timestamp) {
        PriceInfo memory info = latestPrice[basketId];
        return (info.price, info.timestamp);
    }
}
