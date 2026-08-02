// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ConfigureBaskets} from "../script/ConfigureBaskets.s.sol";

contract ConfigureBasketsTest is Test {
    ConfigureBaskets internal script;

    function setUp() public {
        script = new ConfigureBaskets();
    }

    function testMonthFromTimestamp() public {
        // 2026-01-01 00:00:00 UTC
        assertEq(script._monthFromTimestamp(1767225600), 1);
        // 2026-08-15 12:00:00 UTC
        assertEq(script._monthFromTimestamp(1786795200), 8);
        // 2025-12-31 23:59:59 UTC
        assertEq(script._monthFromTimestamp(1767225599), 12);
        // 2027-01-01 00:00:00 UTC
        assertEq(script._monthFromTimestamp(1767225600 + 365 days), 1);
    }

    function testMonthName() public {
        assertEq(script._monthName(8), "AUGUST");
        assertEq(script._monthName(1), "JANUARY");
        assertEq(script._monthName(12), "DECEMBER");
    }

    function testYearFromTimestamp() public {
        assertEq(script._yearFromTimestamp(1767225600), 2026); // 2026-01-01
        assertEq(script._yearFromTimestamp(1767225599), 2025); // 2025-12-31 23:59:59
        assertEq(script._yearFromTimestamp(1767225600 + 365 days), 2027);
    }

    function testUintToString() public {
        assertEq(script._uintToString(2026), "2026");
        assertEq(script._uintToString(0), "0");
        assertEq(script._uintToString(12), "12");
    }

    function testIsTemplate() public {
        assertTrue(script._isTemplate("TOP20-{MONTH}"));
        assertTrue(script._isTemplate("TOP20-{month}"));
        assertTrue(script._isTemplate("TOP20-<MONTH>"));
        assertTrue(script._isTemplate("TOP20-%MONTH%"));
        assertTrue(script._isTemplate("TOP20-MONTH_OF_THE_YEAR"));
        assertTrue(script._isTemplate("TOP20-MONTH OF THE YEAR"));
        assertFalse(script._isTemplate("TOP20-AUGUST"));
        assertFalse(script._isTemplate("TOP20-JULY"));
    }

    function testRenderTemplate() public {
        assertEq(script._renderTemplate("TOP20-{MONTH}", "AUGUST", "2026"), "TOP20-AUGUST");
        assertEq(script._renderTemplate("TOP20-{MONTH}", "SEPTEMBER", "2026"), "TOP20-SEPTEMBER");
        assertEq(script._renderTemplate("TOP20-{month}", "AUGUST", "2026"), "TOP20-AUGUST");
        assertEq(script._renderTemplate("TOP20-MONTH_OF_THE_YEAR", "AUGUST", "2026"), "TOP20-AUGUST");
        assertEq(script._renderTemplate("TOP20-{MONTH}-{YEAR}", "SEPTEMBER", "2027"), "TOP20-SEPTEMBER-2027");
    }

    function testExpandBasketsExpandsTemplates() public {
        // Fresh test env timestamp is 1970-01-01 -> month 1 (JANUARY)
        string[] memory expanded = script._expandBaskets("TOP20-{MONTH}");
        assertEq(expanded.length, 2);
        assertEq(expanded[0], "TOP20-JANUARY");
        assertEq(expanded[1], "TOP20-FEBRUARY");

        vm.warp(1767225600 + 212 days + 3 days); // 2026-08-04 -> AUGUST
        expanded = script._expandBaskets("TOP20-MONTH_OF_THE_YEAR,TOP100-JULY");
        assertEq(expanded.length, 3);
        assertEq(expanded[0], "TOP20-AUGUST");
        assertEq(expanded[1], "TOP20-SEPTEMBER");
        assertEq(expanded[2], "TOP100-JULY");
    }

    function testExpandBasketsDecemberRollover() public {
        vm.warp(1767225600 + 334 days); // 2026-12-01 -> DECEMBER, next JANUARY
        string[] memory expanded = script._expandBaskets("TOP20-{MONTH}");
        assertEq(expanded.length, 2);
        assertEq(expanded[0], "TOP20-DECEMBER");
        assertEq(expanded[1], "TOP20-JANUARY-2027");

        expanded = script._expandBaskets("TOP20-{MONTH}-{YEAR}");
        assertEq(expanded.length, 2);
        assertEq(expanded[0], "TOP20-DECEMBER-2026");
        assertEq(expanded[1], "TOP20-JANUARY-2027");
    }
}
