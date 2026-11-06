// V2 protocol helpers. Not yet wired to the legacy /orders settlement path:
// that path cannot safely execute these signatures without the reviewed ledger.
// No Dynamic auth changes, AA connector, paymaster, or trader-key handling.
import { encodeAbiParameters, hashTypedData, keccak256, type Address, type Hex } from "viem";

export const PRICE_DECIMALS = 3;
export const SIZE_DECIMALS = 6;
export const USDC_DECIMALS = 6;
export const PRICE_SCALE = 1_000n;
export const MIN_NOTIONAL_UNITS = 10_000_000n;
export const MAX_NOTIONAL_UNITS = 1_000_000_000n;
const MAX_PRICE = 100_000n;
const MAX_UINT256 = (1n << 256n) - 1n;
const ZERO_ID = `0x${"00".repeat(32)}` as Hex;

export const authorizationTypes = {
  Authorization: [
    { name: "trader", type: "address" },
    { name: "basketId", type: "bytes32" },
    { name: "orderId", type: "bytes32" },
    { name: "side", type: "uint8" },
    { name: "size", type: "uint256" },
    { name: "maxNotional", type: "uint256" },
    { name: "minPrice", type: "uint256" },
    { name: "maxPrice", type: "uint256" },
    { name: "leverage", type: "uint256" },
    { name: "nonce", type: "uint256" },
    { name: "deadline", type: "uint256" },
    { name: "fillOrKill", type: "bool" },
    { name: "reduceOnly", type: "bool" },
    { name: "positionId", type: "bytes32" },
  ],
} as const;

export interface TradeAuthorization {
  trader: Address;
  basketId: Hex;
  orderId: Hex;
  side: 0 | 1;
  size: bigint;
  maxNotional: bigint;
  minPrice: bigint;
  maxPrice: bigint;
  leverage: bigint;
  nonce: bigint;
  deadline: bigint;
  fillOrKill: boolean;
  reduceOnly: boolean;
  positionId: Hex;
}

/** ABI intent that the V2 ledger can enforce; closing/OCO is not supported. */
export function openingIntent(args: {
  kind: 'limit' | 'market' | 'stop';
  salt: Hex;
  triggerPrice?: bigint;
}): { intent: Hex; orderId: Hex } {
  const kind = { limit: 0, market: 1, stop: 2 }[args.kind];
  const trigger = args.triggerPrice ?? 0n;
  if (!/^0x[0-9a-fA-F]{64}$/.test(args.salt) || BigInt(args.salt) === 0n) {
    throw new Error('An order needs a unique nonzero bytes32 salt.');
  }
  if (args.kind === 'stop' ? trigger <= 0n || trigger > 100_000n : trigger !== 0n) {
    throw new Error('Invalid opening-order trigger price.');
  }
  const intent = encodeAbiParameters(
    [
      { type: 'uint8' }, { type: 'uint256' }, { type: 'bytes32' },
      { type: 'bytes32' }, { type: 'bytes32' },
    ],
    [kind, trigger, ZERO_ID, ZERO_ID, args.salt],
  );
  return { intent, orderId: keccak256(intent) };
}

/** Signed reduce-only lot replacement. Bracket orders must close a full lot. */
export function closingIntent(args: {
  kind: 'limit' | 'market' | 'stop_loss' | 'take_profit';
  salt: Hex;
  positionId: Hex;
  triggerPrice?: bigint;
  ocoGroup?: Hex;
}): { intent: Hex; orderId: Hex } {
  const kind = { limit: 0, market: 1, stop_loss: 3, take_profit: 4 }[args.kind];
  const trigger = args.triggerPrice ?? 0n;
  const group = args.ocoGroup ?? ZERO_ID;
  if (!/^0x[0-9a-fA-F]{64}$/.test(args.salt) || BigInt(args.salt) === 0n ||
      !/^0x[0-9a-fA-F]{64}$/.test(args.positionId) || BigInt(args.positionId) === 0n ||
      !/^0x[0-9a-fA-F]{64}$/.test(group)) {
    throw new Error('Close requires a nonzero lot ID and unique bytes32 salt.');
  }
  if (kind >= 3 ? trigger <= 0n || trigger > 100_000n || BigInt(group) === 0n
                : trigger !== 0n || BigInt(group) !== 0n) {
    throw new Error('Invalid close trigger or OCO group.');
  }
  const intent = encodeAbiParameters(
    [
      { type: 'uint8' }, { type: 'uint256' }, { type: 'bytes32' },
      { type: 'bytes32' }, { type: 'bytes32' },
    ],
    [kind, trigger, group, args.positionId, args.salt],
  );
  return { intent, orderId: keccak256(intent) };
}

/** Decimal strings only; never turn a binary float into a signed amount. */
export function exactUnits(value: string, decimals: number): bigint {
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 6) {
    throw new Error("Unsupported decimal precision.");
  }
  if (
    typeof value !== "string" ||
    value.length > 160 ||
    !/^\d+(?:\.\d+)?$/.test(value)
  ) {
    throw new Error("Enter a finite, positive decimal amount.");
  }
  const [whole, fraction = ""] = value.split(".");
  if (/[^0]/.test(fraction.slice(decimals))) {
    throw new Error(`Use at most ${decimals} decimal places.`);
  }
  const units =
    BigInt(whole) * 10n ** BigInt(decimals) +
    BigInt(fraction.slice(0, decimals).padEnd(decimals, "0") || "0");
  if (units <= 0n || units > MAX_UINT256)
    throw new Error("Amount is outside the supported range.");
  return units;
}

export function priceUnits(value: string): bigint {
  const units = exactUnits(value, PRICE_DECIMALS);
  if (units > MAX_PRICE)
    throw new Error("Price cannot exceed 100 index points.");
  return units;
}

export function sizeUnits(value: string): bigint {
  return exactUnits(value, SIZE_DECIMALS);
}

function assertUint(value: bigint): void {
  if (typeof value !== "bigint" || value < 0n || value > MAX_UINT256) {
    throw new Error("Expected a uint256 integer.");
  }
}

export function notionalUnits(
  size: bigint,
  price: bigint,
  roundUp = true,
): bigint {
  assertUint(size);
  assertUint(price);
  const product = size * price;
  const value = (product + (roundUp ? PRICE_SCALE - 1n : 0n)) / PRICE_SCALE;
  assertUint(value);
  return value;
}

function isAddress(value: string): value is Address {
  return /^0x[0-9a-fA-F]{40}$/.test(value) && BigInt(value) !== 0n;
}

export function validateAuthorization(a: TradeAuthorization): void {
  if (!isAddress(a.trader)) throw new Error("Invalid trader address.");
  for (const id of [a.basketId, a.orderId, a.positionId]) {
    if (!/^0x[0-9a-fA-F]{64}$/.test(id))
      throw new Error("Invalid bytes32 identifier.");
  }
  if (BigInt(a.basketId) === 0n || BigInt(a.orderId) === 0n)
    throw new Error("Missing order identity.");
  for (const value of [
    a.size,
    a.maxNotional,
    a.minPrice,
    a.maxPrice,
    a.leverage,
    a.nonce,
    a.deadline,
  ]) {
    assertUint(value);
  }
  if ((a.side !== 0 && a.side !== 1) || a.size === 0n)
    throw new Error("Invalid side or size.");
  if (
    a.maxNotional < MIN_NOTIONAL_UNITS ||
    a.maxNotional > MAX_NOTIONAL_UNITS
  ) {
    throw new Error("Order notional must be between $10 and $1,000 USDC.");
  }
  if (a.minPrice === 0n || a.minPrice > a.maxPrice || a.maxPrice > MAX_PRICE) {
    throw new Error("Invalid execution-price bounds.");
  }
  if (a.leverage < 1n || a.leverage > 5n)
    throw new Error("Leverage must be between 1x and 5x.");
  if (typeof a.fillOrKill !== "boolean" || typeof a.reduceOnly !== "boolean") {
    throw new Error("Invalid order flags.");
  }
  if (a.reduceOnly && a.positionId.toLowerCase() === ZERO_ID) {
    throw new Error("Reduce-only orders must identify the current position.");
  }
}

export function authorizationTypedData(
  chainId: number,
  executor: Address,
  authorization: TradeAuthorization,
) {
  if (!Number.isSafeInteger(chainId) || chainId <= 0 || !isAddress(executor)) {
    throw new Error("Invalid execution domain.");
  }
  validateAuthorization(authorization);
  return {
    domain: {
      name: "Xleuth Orders",
      version: "2",
      chainId,
      verifyingContract: executor,
    },
    types: authorizationTypes,
    primaryType: "Authorization" as const,
    message: authorization,
  };
}

export function authorizationDigest(
  chainId: number,
  executor: Address,
  authorization: TradeAuthorization,
): Hex {
  return hashTypedData(
    authorizationTypedData(chainId, executor, authorization),
  );
}

type AuthorizationTypedData = ReturnType<typeof authorizationTypedData>;

export interface AuthorizationSigner {
  account?: { address: string } | null;
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  signTypedData?: (
    args: AuthorizationTypedData & { account: Address },
  ) => Promise<Hex>;
}

/** Ask the existing wallet to sign. Never switch identities/chains silently. */
export async function signAuthorization(args: {
  client: AuthorizationSigner;
  chainId: number;
  executor: Address;
  authorization: TradeAuthorization;
}): Promise<Hex> {
  const { client, chainId, executor, authorization } = args;
  const data = authorizationTypedData(chainId, executor, authorization);
  if (
    client.account?.address.toLowerCase() !== authorization.trader.toLowerCase()
  ) {
    throw new Error(
      "The signing wallet does not match the authenticated trader.",
    );
  }
  const chain = await client.request({ method: "eth_chainId" });
  if (
    typeof chain !== "string" ||
    !/^0x[0-9a-f]+$/i.test(chain) ||
    BigInt(chain) !== BigInt(chainId)
  ) {
    throw new Error(
      "Switch your wallet to the configured trading network before signing.",
    );
  }
  const signature = client.signTypedData
    ? await client.signTypedData({ ...data, account: authorization.trader })
    : await client.request({
        method: "eth_signTypedData_v4",
        params: [
          authorization.trader,
          JSON.stringify(
            {
              ...data,
              types: {
                EIP712Domain: [
                  { name: "name", type: "string" },
                  { name: "version", type: "string" },
                  { name: "chainId", type: "uint256" },
                  { name: "verifyingContract", type: "address" },
                ],
                ...data.types,
              },
            },
            (_key, value) =>
              typeof value === "bigint" ? value.toString() : value,
          ),
        ],
      });
  if (
    typeof signature !== "string" ||
    !/^0x(?:[0-9a-fA-F]{2})*$/.test(signature)
  ) {
    throw new Error("The wallet did not return a valid signature.");
  }
  return signature as Hex;
}
