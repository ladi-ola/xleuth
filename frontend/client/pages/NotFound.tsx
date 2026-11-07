import { useLocation, Link } from "react-router-dom";
import { useEffect } from "react";
import { AppShell } from "@/components/xleuth/AppShell";
import { usePageMeta } from "@/hooks/use-page-meta";

// Branded 404 inside the shared trading shell.
// Note: with the static SPA 200-rewrite, unknown URLs return HTTP 200 serving
// this page client-side — a true 404 status needs edge config, documented in
// the final QA report. Vercel's non-root noindex header covers this route.
const NotFound = () => {
  const location = useLocation();

  usePageMeta({
    title: "Page not found — Xleuth (testnet)",
    description:
      "The page you asked for does not exist. Return to the Xleuth testnet markets.",
    path: location.pathname,
  });

  useEffect(() => {
    console.error(
      "404 Error: User attempted to access non-existent route:",
      location.pathname,
    );
  }, [location.pathname]);

  const isMarketSlug = location.pathname.startsWith("/market/");
  const slug = isMarketSlug ? location.pathname.split("/market/")[1] : null;

  return (
    <AppShell>
      <div className="xleuth-not-found">
        <strong>404</strong>
        <p>
          {slug
            ? `Unknown basket "${slug}". It may have expired, been renamed, or never existed.`
            : "This page does not exist."}
        </p>
        <div>
          <Link to="/app">
            Launch app
          </Link>
          <Link to="/explore">
            Browse baskets
          </Link>
        </div>
      </div>
    </AppShell>
  );
};

export default NotFound;
