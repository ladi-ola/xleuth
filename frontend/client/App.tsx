import "./entry.css";

import { lazy, Suspense, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import Landing from "./pages/Landing";

const TradingApp = lazy(() => import("./TradingApp"));

function RouteIndexing() {
  const { pathname } = useLocation();

  useEffect(() => {
    document.querySelector('meta[name="robots"]')?.remove();
    if (pathname !== "/") {
      const meta = document.createElement("meta");
      meta.name = "robots";
      meta.content = "noindex, nofollow";
      document.head.appendChild(meta);
    }
  }, [pathname]);

  return null;
}

function App() {
  return (
    <BrowserRouter>
      <RouteIndexing />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="*" element={<Suspense fallback={<p role="status">Loading app…</p>}><TradingApp /></Suspense>} />
      </Routes>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
