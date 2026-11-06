import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Routes, Route, useLocation } from "react-router-dom";
import {
  DynamicContextProvider,
  overrideNetworkRpcUrl,
} from "@dynamic-labs/sdk-react-core";
import { EthereumWalletConnectors } from "@dynamic-labs/ethereum";
import { ZeroDevSmartWalletConnectors } from "@dynamic-labs/ethereum-aa";
import { useEffect } from "react";
import { ThemeProvider, useTheme } from "next-themes";
import { DYNAMIC_ENVIRONMENT_ID } from "@/lib/dynamic";
import { pageview } from "@/lib/analytics";
import { CookieNotice } from "@/components/xleuth/CookieNotice";
import { ErrorBoundary } from "@/components/xleuth/ErrorBoundary";
import Markets from "./pages/Markets";
import Explore from "./pages/Explore";
import Portfolio from "./pages/Portfolio";
import Account from "./pages/Account";
import NotFound from "./pages/NotFound";
import Privacy from "./pages/Privacy";
import Terms from "./pages/Terms";
import HowItWorks from "./pages/HowItWorks";
import LegalRiskDisclosure from "./pages/LegalRiskDisclosure";
import Support from "./pages/Support";

const queryClient = new QueryClient();

// Dynamic's project settings point Polygon Amoy at
// `https://rpc-amoy.polygon.technology`, which no longer resolves. The SDK
// retries `eth_chainId` against it forever, so ZeroDev can never prepare a
// user operation and deposits hang. Override both the public and private RPC
// lists at runtime with working Amoy endpoints.
const AMOY_RPC_URLS = [
  "https://polygon-amoy-bor-rpc.publicnode.com",
  "https://polygon-amoy.drpc.org",
];
const AMOY_CHAIN_ID = 80002;

const evmNetworkOverrides = (
  networks: Parameters<typeof overrideNetworkRpcUrl>[0],
) => {
  const withPrivateRpc = overrideNetworkRpcUrl(networks, {
    [String(AMOY_CHAIN_ID)]: AMOY_RPC_URLS,
  });
  return withPrivateRpc.map((network) =>
    Number(network.chainId) === AMOY_CHAIN_ID
      ? { ...network, rpcUrls: AMOY_RPC_URLS }
      : network,
  );
};

function RouteTracker() {
  const location = useLocation();
  useEffect(() => {
    pageview(location.pathname);
  }, [location.pathname]);
  return null;
}

function ThemedApp() {
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    meta?.setAttribute(
      "content",
      resolvedTheme === "dark" ? "#141217" : "#f8f8fa",
    );
  }, [resolvedTheme]);

  return (
    <DynamicContextProvider
      settings={{
        environmentId: DYNAMIC_ENVIRONMENT_ID,
        // The Dynamic project has ZeroDev account abstraction enabled. The
        // ZeroDev connector must be registered too, otherwise email/social
        // users get a fallback wallet with no signer and cannot deposit.
        walletConnectors: [
          EthereumWalletConnectors,
          ZeroDevSmartWalletConnectors,
        ],
        overrides: {
          evmNetworks: evmNetworkOverrides,
        },
      }}
      theme={resolvedTheme === "dark" ? "dark" : "light"}
    >
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <ErrorBoundary>
            <Toaster />
            <Sonner />
            <>
              <RouteTracker />
              <CookieNotice />
              <Routes>
                <Route path="/app" element={<Markets />} />
                <Route path="/market/:slug" element={<Markets />} />
                <Route path="/explore" element={<Explore />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/account" element={<Account />} />
                <Route path="/how-it-works" element={<HowItWorks />} />
                <Route
                  path="/legal-risk-disclosure"
                  element={<LegalRiskDisclosure />}
                />
                <Route path="/support" element={<Support />} />
                <Route path="/privacy" element={<Privacy />} />
                <Route path="/terms" element={<Terms />} />
                {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                <Route path="*" element={<NotFound />} />
              </Routes>
            </>
          </ErrorBoundary>
        </TooltipProvider>
      </QueryClientProvider>
    </DynamicContextProvider>
  );
}

const TradingApp = () => (
  <ThemeProvider
    attribute="class"
    defaultTheme="light"
    enableSystem={false}
    storageKey="xleuth-theme"
    disableTransitionOnChange
  >
    <ThemedApp />
  </ThemeProvider>
);

export default TradingApp;
