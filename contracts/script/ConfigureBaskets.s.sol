// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {IndexOracleConsumer} from "../src/IndexOracleConsumer.sol";

/// @title ConfigureBaskets
/// @notice Seeds signed index prices for the active baskets on-chain so the
///         PositionManager can open positions immediately after deploy.
///         Reads from contracts/.env:
///           INDEX_ORACLE_CONSUMER_ADDRESS (required)
///           ACTIVE_BASKETS (comma-separated; month templates are expanded
///             to the current month (active) and the next month (upcoming),
///             e.g. TOP20-{MONTH} -> TOP20-AUGUST, TOP20-SEPTEMBER)
///           BASKET_INITIAL_PRICES (comma-separated ints, same length as the
///             expanded list; defaults to 50 for each basket if unset)
///           ORACLE_SIGNER_PRIVATE_KEY (falls back to DEPLOYER_PRIVATE_KEY)
///         The Week-4 oracle-service will take over pushing live prices.
///         Usage:
///           forge script script/ConfigureBaskets.s.sol:ConfigureBaskets \
///             --rpc-url $RPC_URL --private-key $ORACLE_SIGNER_PRIVATE_KEY --broadcast
contract ConfigureBaskets is Script {
    function run() external {
        address consumer = vm.envAddress("INDEX_ORACLE_CONSUMER_ADDRESS");
        string[] memory basketNames = _expandBaskets(vm.envString("ACTIVE_BASKETS"));

        uint256[] memory prices = new uint256[](basketNames.length);
        if (
            !vm.envExists("BASKET_INITIAL_PRICES")
                || bytes(vm.envString("BASKET_INITIAL_PRICES")).length == 0
        ) {
            for (uint256 i = 0; i < prices.length; i++) {
                prices[i] = 50;
            }
        } else {
            string[] memory priceStrs = _split(vm.envString("BASKET_INITIAL_PRICES"), ",");
            require(priceStrs.length == basketNames.length, "prices/baskets length mismatch");
            for (uint256 i = 0; i < prices.length; i++) {
                prices[i] = vm.parseUint(priceStrs[i]);
            }
        }

        uint256 deployerKey = _envPrivateKey("DEPLOYER_PRIVATE_KEY");
        uint256 oracleKey = vm.envOr("ORACLE_SIGNER_PRIVATE_KEY", deployerKey);
        address signer = vm.addr(oracleKey);

        vm.startBroadcast(oracleKey);
        IndexOracleConsumer oracle = IndexOracleConsumer(consumer);
        for (uint256 i = 0; i < basketNames.length; i++) {
            bytes32 basketId = keccak256(abi.encodePacked(basketNames[i]));
            uint256 timestamp = block.timestamp;
            bytes memory sig = _signPriceUpdate(oracleKey, consumer, basketId, prices[i], timestamp);

            oracle.pushPrice(basketId, prices[i], timestamp, sig);
            console2.log(
                "seeded %s (%s) at price %s", basketNames[i], vm.toString(basketId), prices[i]
            );
        }
        vm.stopBroadcast();

        console2.log("oracle signer: %s", signer);
        console2.log("ConfigureBaskets: done for %s baskets", basketNames.length);
    }

    /// @dev Reads a private key from env, tolerating a missing 0x prefix.
    function _envPrivateKey(string memory name) internal returns (uint256) {
        string memory value = vm.envString(name);
        if (bytes(value).length >= 2 && bytes(value)[0] == "0" && bytes(value)[1] == "x") {
            return vm.parseUint(value);
        }
        return vm.parseUint(string.concat("0x", value));
    }

    function _signPriceUpdate(
        uint256 key,
        address consumer,
        bytes32 basketId,
        uint256 price,
        uint256 timestamp
    ) internal view returns (bytes memory) {
        bytes32 typeHash = keccak256(
            "PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"
        );
        bytes32 structHash = keccak256(abi.encode(typeHash, basketId, price, timestamp));
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Xleuth Index Oracle"),
                keccak256("1"),
                block.chainid,
                consumer
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    /// @dev Expands the ACTIVE_BASKETS env list: entries containing a month
    ///      placeholder ({MONTH}, <MONTH>, %MONTH% or MONTH_OF_THE_YEAR
    ///      variants) yield the current month and the next month; literal
    ///      names are passed through unchanged. {YEAR}/<YEAR>/%YEAR% markers
    ///      are substituted with the year; a December rollover gets an
    ///      explicit -YYYY suffix so the January name stays unambiguous.
    function _expandBaskets(string memory raw) public view returns (string[] memory) {
        string[] memory parts = _split(raw, ",");
        uint256 currentMonth = _monthFromTimestamp(block.timestamp);
        uint256 nextMonth = currentMonth == 12 ? 1 : currentMonth + 1;
        uint256 year = _yearFromTimestamp(block.timestamp);
        uint256 nextYear = currentMonth == 12 ? year + 1 : year;

        uint256 count = 0;
        for (uint256 i = 0; i < parts.length; i++) {
            if (bytes(parts[i]).length == 0) continue;
            count += _isTemplate(parts[i]) ? 2 : 1;
        }

        string[] memory result = new string[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < parts.length; i++) {
            string memory part = parts[i];
            if (bytes(part).length == 0) continue;
            if (_isTemplate(part)) {
                result[idx++] = _renderTemplate(part, _monthName(currentMonth), _uintToString(year));
                string memory nxt = _renderTemplate(part, _monthName(nextMonth), _uintToString(nextYear));
                if (currentMonth == 12 && !_containsInsensitive(bytes(part), "{YEAR}")) {
                    nxt = string.concat(nxt, "-", _uintToString(nextYear));
                }
                result[idx++] = nxt;
            } else {
                result[idx++] = part;
            }
        }
        return result;
    }

    /// @dev True if the name carries a month placeholder instead of a month.
    function _isTemplate(string memory name) public pure returns (bool) {
        bytes memory b = bytes(name);
        if (_containsInsensitive(b, "{MONTH}")) return true;
        if (_containsInsensitive(b, "<MONTH>")) return true;
        if (_containsInsensitive(b, "%MONTH%")) return true;
        if (_containsInsensitive(b, "MONTH_OF_THE_YEAR")) return true;
        if (_containsInsensitive(b, "MONTH OF THE YEAR")) return true;
        if (_containsInsensitive(b, "MONTH-OF-THE-YEAR")) return true;
        return false;
    }

    /// @dev Substitutes the month and (if present) the year placeholder in
    ///      `name` with the given values. Supports {MONTH}, <MONTH>, %MONTH%
    ///      and the phrase MONTH OF THE YEAR (separators _, space or -).
    function _renderTemplate(
        string memory name,
        string memory monthName,
        string memory yearStr
    ) public pure returns (string memory) {
        bytes memory src = bytes(name);
        (int256 found, uint256 mlen) = _findMonthPlaceholder(src);
        require(found >= 0, "ConfigureBaskets: template missing {MONTH}");
        uint256 idx = uint256(found);

        bytes memory m = bytes(monthName);
        bytes memory step1 = new bytes(src.length - mlen + m.length);
        for (uint256 i = 0; i < idx; i++) step1[i] = src[i];
        for (uint256 i = 0; i < m.length; i++) step1[idx + i] = m[i];
        for (uint256 i = idx + mlen; i < src.length; i++) {
            step1[i - mlen + m.length] = src[i];
        }

        bytes memory yearMarker = bytes("{YEAR}");
        int256 yearFound = _findInsensitive(step1, yearMarker);
        if (yearFound < 0) return string(step1);
        uint256 yIdx = uint256(yearFound);
        uint256 ylen = yearMarker.length;
        bytes memory y = bytes(yearStr);
        bytes memory out = new bytes(step1.length - ylen + y.length);
        for (uint256 i = 0; i < yIdx; i++) out[i] = step1[i];
        for (uint256 i = 0; i < y.length; i++) out[yIdx + i] = y[i];
        for (uint256 i = yIdx + ylen; i < step1.length; i++) {
            out[i - ylen + y.length] = step1[i];
        }
        return string(out);
    }

    /// @dev Locates the month placeholder in `b`; returns its start index and
    ///      length, or (-1, 0) when absent. Handles {MONTH}, <MONTH>, %MONTH%
    ///      and the phrase MONTH[sep]OF[sep]THE[sep]YEAR (sep = _, space or -).
    function _findMonthPlaceholder(bytes memory b)
        internal
        pure
        returns (int256 found_, uint256 len_)
    {
        bytes[3] memory markers = [bytes("{MONTH}"), bytes("<MONTH>"), bytes("%MONTH%")];
        for (uint256 k = 0; k < markers.length; k++) {
            int256 idx = _findInsensitive(b, markers[k]);
            if (idx >= 0) return (idx, markers[k].length);
        }
        for (uint256 i = 0; i + 5 <= b.length; i++) {
            if (!_wordMatches(b, i, "MONTH")) continue;
            uint256 j = _skipSeparators(b, i + 5);
            if (!_wordMatches(b, j, "OF")) continue;
            j = _skipSeparators(b, j + 2);
            if (!_wordMatches(b, j, "THE")) continue;
            j = _skipSeparators(b, j + 3);
            if (!_wordMatches(b, j, "YEAR")) continue;
            return (int256(i), j + 4 - i);
        }
        return (-1, 0);
    }

    function _wordMatches(bytes memory b, uint256 i, string memory word)
        internal
        pure
        returns (bool)
    {
        bytes memory w = bytes(word);
        if (i + w.length > b.length) return false;
        for (uint256 j = 0; j < w.length; j++) {
            uint8 a = uint8(b[i + j]);
            uint8 c = uint8(w[j]);
            if (a >= 65 && a <= 90) a += 32;
            if (c >= 65 && c <= 90) c += 32;
            if (a != c) return false;
        }
        return true;
    }

    function _skipSeparators(bytes memory b, uint256 i) internal pure returns (uint256) {
        while (i < b.length && (b[i] == "_" || b[i] == " " || b[i] == "-")) i++;
        return i;
    }

    /// @dev Case-insensitive substring search; returns the byte index or -1.
    function _findInsensitive(bytes memory haystack, bytes memory needle)
        public
        pure
        returns (int256)
    {
        if (needle.length > haystack.length) return -1;
        for (uint256 i = 0; i + needle.length <= haystack.length; i++) {
            bool ok = true;
            for (uint256 j = 0; j < needle.length; j++) {
                uint8 a = uint8(haystack[i + j]);
                uint8 b = uint8(needle[j]);
                if (a >= 65 && a <= 90) a += 32;
                if (b >= 65 && b <= 90) b += 32;
                if (a != b) {
                    ok = false;
                    break;
                }
            }
            if (ok) return int256(i);
        }
        return -1;
    }

    function _containsInsensitive(bytes memory haystack, bytes memory needle)
        internal
        pure
        returns (bool)
    {
        return _findInsensitive(haystack, needle) >= 0;
    }

    /// @dev Month number (1-12) for a unix timestamp.
    function _monthFromTimestamp(uint256 ts) public pure returns (uint256) {
        // Howard Hinnant's civil_from_days (days since epoch -> month).
        uint256 z = ts / 86400 + 719468;
        uint256 era = z / 146097;
        uint256 doe = z - era * 146097;
        uint256 yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        uint256 doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        uint256 mp = (5 * doy + 2) / 153;
        return mp < 10 ? mp + 3 : mp - 9;
    }

    /// @dev Year for a unix timestamp (same civil algorithm as _monthFromTimestamp).
    /// @dev Year for a unix timestamp (same civil algorithm as _monthFromTimestamp).
    ///      The era-based year gains +1 for Jan/Feb months (the epoch is
    ///      0000-03-01), as in Hinnant's civil_from_days.
    function _yearFromTimestamp(uint256 ts) public pure returns (uint256) {
        uint256 z = ts / 86400 + 719468;
        uint256 era = z / 146097;
        uint256 doe = z - era * 146097;
        uint256 yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        uint256 doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        uint256 mp = (5 * doy + 2) / 153;
        uint256 m = mp < 10 ? mp + 3 : mp - 9;
        uint256 y = yoe + era * 400;
        return m <= 2 ? y + 1 : y;
    }

    function _uintToString(uint256 value) public pure returns (string memory) {
        if (value == 0) return "0";
        uint256 tmp = value;
        uint256 digits = 0;
        while (tmp > 0) {
            tmp /= 10;
            digits++;
        }
        bytes memory out = new bytes(digits);
        while (value > 0) {
            out[--digits] = bytes1(uint8(48 + (value % 10)));
            value /= 10;
        }
        return string(out);
    }

    function _monthName(uint256 month) public pure returns (string memory) {
        string[12] memory names = [
            "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
            "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
        ];
        return names[month - 1];
    }

    function _split(string memory input, string memory delimiter)
        internal
        pure
        returns (string[] memory)
    {
        bytes memory del = bytes(delimiter);
        bytes memory buf = new bytes(0);
        uint256 parts = 1;
        for (uint256 i = 0; i < bytes(input).length; i++) {
            if (bytes(input)[i] == del[0]) parts++;
        }

        string[] memory result = new string[](parts);
        uint256 part = 0;
        for (uint256 i = 0; i < bytes(input).length + 1; i++) {
            bool atEnd = i == bytes(input).length;
            bool isDelim = !atEnd && bytes(input)[i] == del[0];
            if (atEnd || isDelim) {
                result[part] = string(buf);
                part++;
                buf = new bytes(0);
            } else {
                bytes memory tmp = new bytes(buf.length + 1);
                for (uint256 j = 0; j < buf.length; j++) {
                    tmp[j] = buf[j];
                }
                tmp[buf.length] = bytes(input)[i];
                buf = tmp;
            }
        }
        return result;
    }
}
