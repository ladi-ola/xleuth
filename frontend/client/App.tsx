import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { createRoot } from "react-dom/client";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { DynamicContextProvider } from "@dynamic-labs/sdk-react-core";
import { EthereumWalletConnectors } from "@dynamic-labs/ethereum";
import { useEffect } from "react";
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

function RouteTracker() {
  const location = useLocation();
  useEffect(() => {
    pageview(location.pathname);
  }, [location.pathname]);
  return null;
}

const App = () => (
  <DynamicContextProvider
    settings={{
      environmentId: DYNAMIC_ENVIRONMENT_ID,
      walletConnectors: [EthereumWalletConnectors],
    }}
  >
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <ErrorBoundary>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <RouteTracker />
          <CookieNotice />
          <Routes>
            <Route path="/" element={<Markets />} />
            <Route path="/market/:slug" element={<Markets />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/account" element={<Account />} />
            <Route path="/how-it-works" element={<HowItWorks />} />
            <Route path="/legal-risk-disclosure" element={<LegalRiskDisclosure />} />
            <Route path="/support" element={<Support />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
        </ErrorBoundary>
      </TooltipProvider>
    </QueryClientProvider>
  </DynamicContextProvider>
);

createRoot(document.getElementById("root")!).render(<App />);
