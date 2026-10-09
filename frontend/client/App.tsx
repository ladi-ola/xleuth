import "./global.css";

import { Toaster } from "@/components/ui/toaster";
import { createRoot } from "react-dom/client";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { DynamicContextProvider } from "@dynamic-labs/sdk-react-core";
import { EthereumWalletConnectors } from "@dynamic-labs/ethereum";
import { DYNAMIC_ENVIRONMENT_ID } from "@/lib/dynamic";
import Markets from "./pages/Markets";
import Explore from "./pages/Explore";
import Portfolio from "./pages/Portfolio";
import Account from "./pages/Account";
import NotFound from "./pages/NotFound";
import HowItWorks from "./pages/HowItWorks";
import LegalRiskDisclosure from "./pages/LegalRiskDisclosure";
import Support from "./pages/Support";

const queryClient = new QueryClient();

const App = () => (
  <DynamicContextProvider
    settings={{
      environmentId: DYNAMIC_ENVIRONMENT_ID,
      walletConnectors: [EthereumWalletConnectors],
    }}
  >
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Markets />} />
            <Route path="/market/:slug" element={<Markets />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/account" element={<Account />} />
            <Route path="/how-it-works" element={<HowItWorks />} />
            <Route path="/legal-risk-disclosure" element={<LegalRiskDisclosure />} />
            <Route path="/support" element={<Support />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </DynamicContextProvider>
);

createRoot(document.getElementById("root")!).render(<App />);
