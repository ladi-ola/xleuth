// Polygon Amoy contracts used by the browser wallet.
//
// The app only needs two writes today: approve the vault to pull test-USDC,
// and deposit that USDC into the vault. Both are encoded by hand below so the
// frontend does not need to add viem/wagmi as a direct dependency — Dynamic's
// Ethereum connector already exposes a viem WalletClient with `request`.

const DEFAULT_CHAIN_ID = 80002;
const DEFAULT_USDC_ADDRESS = "0xc8783E02f3EE944BdE2990DbcDFefbe8adc3e86D";
const DEFAULT_VAULT_ADDRESS = "0x6dbeEb6a5bE0cD63159b1dBD5525dE125A1CECef";
const DEFAULT_RPC_URL = "https://polygon-amoy-bor-rpc.publicnode.com";
const FALLBACK_RPC_URL = "https://polygon-amoy.drpc.org";

// The old frontend env shipped this address as USDC; it has no contract code
// on Amoy. Ignore it so a stale dashboard/env value cannot break deposits.
const STALE_USDC_ADDRESS = "0x41e94eb019c0762f9bfc4e59b00e5b8a0e7b47d8";

export const CHAIN_ID = Number(import.meta.env.VITE_CHAIN_ID || DEFAULT_CHAIN_ID);
export const CHAIN_ID_HEX = `0x${CHAIN_ID.toString(16)}`;
export const USDC_DECIMALS = 6;

function readAddress(value: string | undefined, fallback: string): `0x${string}` {
  const candidate = (value || "").trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(candidate)) {
    return fallback as `0x${string}`;
  }
  if (candidate.toLowerCase() === STALE_USDC_ADDRESS) {
    return fallback as `0x${string}`;
  }
  return candidate as `0x${string}`;
}

export const USDC_ADDRESS = readAddress(
  import.meta.env.VITE_COLLATERAL_TOKEN_ADDRESS || import.meta.env.VITE_USDC_CONTRACT_ADDRESS,
  DEFAULT_USDC_ADDRESS,
);

export const COLLATERAL_VAULT_ADDRESS = readAddress(
  import.meta.env.VITE_COLLATERAL_VAULT_ADDRESS,
  DEFAULT_VAULT_ADDRESS,
);

export const CHAIN_RPC_URL =
  import.meta.env.VITE_CHAIN_RPC_URL || DEFAULT_RPC_URL;

// Public fallbacks keep receipt polling working when the configured RPC is
// rate-limited (the example env used to point at Alchemy's demo key).
const RPC_URLS: string[] = Array.from(
  new Set(
    [CHAIN_RPC_URL, DEFAULT_RPC_URL, FALLBACK_RPC_URL].filter(
      (url): url is string => typeof url === "string" && url.length > 0,
    ),
  ),
);

const ERC20_APPROVE_SELECTOR = "0x095ea7b3"; // approve(address,uint256)
const ERC20_BALANCE_OF_SELECTOR = "0x70a08231"; // balanceOf(address)
const VAULT_DEPOSIT_SELECTOR = "0xb6b55f25"; // deposit(uint256)

export function toUsdcUnits(amount: number): bigint {
  if (!Number.isFinite(amount) || amount <= 0) return 0n;
  // Amounts come from the API as floats; round to the token's 6 decimals
  // before scaling so 1000.0000000001 cannot produce an off-by-one unit.
  return BigInt(Math.round(amount * 10 ** USDC_DECIMALS));
}

function encodeUint256(value: bigint): string {
  return value.toString(16).padStart(64, "0");
}

function encodeAddress(address: string): string {
  return address.toLowerCase().replace(/^0x/, "").padStart(64, "0");
}

export function buildApproveCalldata(
  spender: string,
  amount: bigint,
): `0x${string}` {
  return `${ERC20_APPROVE_SELECTOR}${encodeAddress(spender)}${encodeUint256(amount)}` as `0x${string}`;
}

export function buildDepositCalldata(amount: bigint): `0x${string}` {
  return `${VAULT_DEPOSIT_SELECTOR}${encodeUint256(amount)}` as `0x${string}`;
}

export function buildBalanceOfCalldata(holder: string): `0x${string}` {
  return `${ERC20_BALANCE_OF_SELECTOR}${encodeAddress(holder)}` as `0x${string}`;
}

interface WalletClientLike {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  account?: { address?: string } | null;
}

export interface DynamicWalletLike {
  address?: string;
  switchNetwork?: (chainId: number | string) => Promise<void>;
  // EthereumWallet exposes this wrapper; prefer it because it also runs the
  // SDK's account sync and transaction-screening hooks.
  getWalletClient?: (chainId?: string) => Promise<WalletClientLike>;
  connector?: {
    getWalletClient?: (
      chainId?: string,
    ) => WalletClientLike | Promise<WalletClientLike | undefined> | undefined;
    // Dynamic's connector takes an object, unlike Wallet.switchNetwork which
    // accepts a bare chain id.
    switchNetwork?: (args: {
      networkName?: string;
      networkChainId?: number | string;
    }) => Promise<void>;
  };
}

async function getWalletClient(wallet: DynamicWalletLike): Promise<WalletClientLike> {
  let client: WalletClientLike | undefined;
  try {
    client = wallet.getWalletClient
      ? await wallet.getWalletClient(String(CHAIN_ID))
      : await wallet.connector?.getWalletClient?.(String(CHAIN_ID));
  } catch {
    client = undefined;
  }
  if (!client) {
    throw new Error(
      "This wallet cannot sign transactions. Reconnect it or use a browser wallet.",
    );
  }
  return client;
}

function isUserRejection(error: unknown): boolean {
  const code = (error as { code?: number | string } | null)?.code;
  return code === 4001 || code === "ACTION_REJECTED";
}

async function ensureChain(
  wallet: DynamicWalletLike,
  client: WalletClientLike,
): Promise<void> {
  // Skip the switch prompt when the wallet is already on Amoy.
  try {
    const current = await client.request({ method: "eth_chainId" });
    if (typeof current === "string" && Number.parseInt(current, 16) === CHAIN_ID) {
      return;
    }
  } catch {
    // Fall through to the switch methods below.
  }

  try {
    if (wallet.switchNetwork) {
      await wallet.switchNetwork(CHAIN_ID);
      return;
    }
    if (wallet.connector?.switchNetwork) {
      await wallet.connector.switchNetwork({ networkChainId: CHAIN_ID });
      return;
    }
  } catch (error) {
    // Do not prompt twice if the user explicitly rejected the switch.
    if (isUserRejection(error)) {
      throw new Error("Switch your wallet to Polygon Amoy and try again.");
    }
    // Otherwise fall through to the EIP-1193 switch; some connectors throw
    // when the wallet is already on the requested chain.
  }

  try {
    await client.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: CHAIN_ID_HEX }],
    });
  } catch (error) {
    if (isUserRejection(error)) {
      throw new Error("Switch your wallet to Polygon Amoy and try again.");
    }
    const code = (error as { code?: number } | null)?.code;
    if (code === 4902) {
      await client.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId: CHAIN_ID_HEX,
            chainName: "Polygon Amoy",
            nativeCurrency: { name: "POL", symbol: "POL", decimals: 18 },
            rpcUrls: [CHAIN_RPC_URL],
            blockExplorerUrls: ["https://amoy.polygonscan.com"],
          },
        ],
      });
      return;
    }
    throw new Error("Switch your wallet to Polygon Amoy and try again.");
  }
}

async function readUsdcBalance(
  client: WalletClientLike,
  owner: string,
): Promise<bigint> {
  const call = {
    to: USDC_ADDRESS,
    data: buildBalanceOfCalldata(owner),
  };
  let result: unknown;
  try {
    result = await client.request({
      method: "eth_call",
      params: [call, "latest"],
    });
  } catch {
    // Some wallet providers do not proxy read calls. Fall back to the public
    // Amoy RPCs so the deposit amount still comes from the chain.
    for (const url of RPC_URLS) {
      try {
        result = await rpcCall(url, "eth_call", [call, "latest"]);
        break;
      } catch {
        // Try the next RPC.
      }
    }
  }
  if (
    typeof result !== "string" ||
    !result.startsWith("0x") ||
    result.length <= 2
  ) {
    throw new Error("Could not read your test-USDC balance. Try again.");
  }
  return BigInt(result);
}

async function sendTransaction(
  client: WalletClientLike,
  from: string,
  to: string,
  data: `0x${string}`,
): Promise<string> {
  const hash = await client.request({
    method: "eth_sendTransaction",
    params: [{ from, to, data }],
  });
  if (typeof hash !== "string" || !hash.startsWith("0x")) {
    throw new Error("Wallet did not return a transaction hash.");
  }
  return hash;
}

async function rpcCall(
  url: string,
  method: string,
  params: unknown[],
): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`RPC HTTP ${response.status}`);
    }
    const body = (await response.json()) as {
      result?: unknown;
      error?: { message?: string };
    };
    if (body.error) {
      throw new Error(body.error.message || "RPC error");
    }
    return body.result;
  } finally {
    clearTimeout(timer);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

type TransactionReceipt = { status?: string } | null;

/** Returns true when a receipt is final; throws when it reverted. */
function isFinalReceipt(receipt: TransactionReceipt): boolean {
  if (!receipt) return false;
  if (receipt.status === "0x0") {
    throw new Error("Transaction reverted on-chain.");
  }
  return true;
}

export async function waitForReceipt(
  hash: string,
  timeoutMs = 120_000,
  client?: WalletClientLike,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;

  while (Date.now() < deadline) {
    // Prefer the wallet's own provider: it is already authenticated and
    // avoids relying on a public RPC's CORS policy. Fall back to HTTP RPCs
    // when the wallet does not implement receipt lookups.
    if (client) {
      let receipt: TransactionReceipt | undefined;
      try {
        receipt = (await client.request({
          method: "eth_getTransactionReceipt",
          params: [hash],
        })) as TransactionReceipt;
      } catch (error) {
        lastError = error;
      }
      if (receipt !== undefined && isFinalReceipt(receipt)) return;
    }

    for (const url of RPC_URLS) {
      let receipt: TransactionReceipt | undefined;
      try {
        receipt = (await rpcCall(url, "eth_getTransactionReceipt", [
          hash,
        ])) as TransactionReceipt;
      } catch (error) {
        lastError = error;
        continue;
      }
      if (isFinalReceipt(receipt)) return;
      // This RPC answered and the tx is still pending; don't hammer the
      // fallback endpoint on the same tick.
      break;
    }
    await sleep(2_000);
  }

  throw new Error(
    `Timed out waiting for the transaction to confirm${
      lastError instanceof Error ? `: ${lastError.message}` : ""
    }. Check your wallet and refresh.`,
  );
}

export interface DepositResult {
  approveTx: string;
  depositTx: string;
}

/**
 * Approve the CollateralVault and deposit test-USDC. With no explicit amount
 * it deposits the full on-chain wallet balance. Both transactions are signed
 * by the connected wallet; the backend never holds user keys.
 */
export async function approveAndDepositToVault(args: {
  wallet: DynamicWalletLike;
  /** Optional subset to deposit; defaults to the full on-chain balance. */
  amountUsdc?: number;
  /** JWT wallet address; refuses to deposit from a different account. */
  expectedAddress?: string;
  onStep?: (step: "approve" | "deposit") => void;
}): Promise<DepositResult> {
  const client = await getWalletClient(args.wallet);
  const from = client.account?.address || args.wallet.address;
  if (!from) {
    throw new Error("Wallet address is unavailable.");
  }
  if (
    args.expectedAddress &&
    from.toLowerCase() !== args.expectedAddress.toLowerCase()
  ) {
    throw new Error(
      "Connected wallet does not match the signed-in account. Reconnect the wallet that owns the test USDC.",
    );
  }

  await ensureChain(args.wallet, client);

  // Read the exact token balance from the chain instead of trusting a cached
  // summary. This also keeps deposits working if the API deployment is older
  // and does not expose `wallet_balance` yet.
  const amount =
    args.amountUsdc !== undefined
      ? toUsdcUnits(args.amountUsdc)
      : await readUsdcBalance(client, from);
  if (amount <= 0n) {
    throw new Error("No test USDC in your wallet to deposit.");
  }

  args.onStep?.("approve");
  const approveTx = await sendTransaction(
    client,
    from,
    USDC_ADDRESS,
    buildApproveCalldata(COLLATERAL_VAULT_ADDRESS, amount),
  );
  await waitForReceipt(approveTx, 120_000, client);

  args.onStep?.("deposit");
  const depositTx = await sendTransaction(
    client,
    from,
    COLLATERAL_VAULT_ADDRESS,
    buildDepositCalldata(amount),
  );
  await waitForReceipt(depositTx, 120_000, client);

  return { approveTx, depositTx };
}
