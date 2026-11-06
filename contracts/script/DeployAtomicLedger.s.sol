// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {AtomicTradeLedger} from "../src/AtomicTradeLedger.sol";
import {SignedOrderExecutor} from "../src/SignedOrderExecutor.sol";

/// @notice New isolated contracts; does not modify or withdraw legacy vault
/// balances. Run ONLY after the signed-order coordinator, close/OCO protocol,
/// frontend and portfolio have passed security review and owner approval.
contract DeployAtomicLedger is Script {
    function run() external {
        require(vm.envOr("ATOMIC_CUTOVER_APPROVED", uint256(0)) == 1, "review and approve atomic cutover first");
        address token = vm.envAddress("TEST_USDC_ADDRESS");
        address oracle = vm.envAddress("INDEX_ORACLE_CONSUMER_ADDRESS");
        address signer = vm.envAddress("SETTLEMENT_SIGNER_ADDRESS");
        address relayer = vm.envAddress("ATOMIC_RELAYER_ADDRESS");
        uint256 age = vm.envUint("MAX_PRICE_STALENESS_SECONDS");
        uint256 deviation = vm.envUint("MAX_EXECUTION_DEVIATION_MILLI_POINTS");
        uint256 settlementAge = vm.envUint("SETTLEMENT_MAX_STALENESS_SECONDS");
        uint256 key = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address owner = vm.addr(key);

        vm.startBroadcast(key);
        AtomicTradeLedger ledger = new AtomicTradeLedger(
            owner, token, oracle, signer, age, deviation, settlementAge
        );
        SignedOrderExecutor executor = new SignedOrderExecutor(address(ledger), relayer);
        ledger.bindExecutor(address(executor));
        vm.stopBroadcast();

        console2.log("ATOMIC_TRADE_LEDGER_ADDRESS=", address(ledger));
        console2.log("SIGNED_ORDER_EXECUTOR_ADDRESS=", address(executor));
    }
}
