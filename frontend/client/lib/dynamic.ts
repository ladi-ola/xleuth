// TODO: set VITE_DYNAMIC_ENVIRONMENT_ID in .env with your Dynamic.xyz environment id.
// Get one at https://app.dynamic.xyz — create an environment, enable embedded wallets +
// social login, and enable the EVM network you deploy to (Polygon Amoy testnet for now).
// Falls back to a placeholder id so the SDK provider doesn't hard-crash the app before a
// real environment id is configured — auth/deposit/faucet calls will simply no-op until then.
export const DYNAMIC_ENVIRONMENT_ID: string =
  import.meta.env.VITE_DYNAMIC_ENVIRONMENT_ID ||
  "00000000-0000-0000-0000-000000000000";

// TODO: replace with the deployed Polygon Amoy testnet chain config / RPC once available.
export const XLEUTH_CHAIN = {
  id: 80002,
  name: "Polygon Amoy",
  network: "amoy",
} as const;

// TODO: drop in the deployed testnet USDC faucet contract address once available.
export const FAUCET_CONTRACT_ADDRESS = "";

// TODO: drop in the deployed index/basket + margin trading contract addresses once available.
export const XLEUTH_INDEX_CONTRACT_ADDRESS = "";
