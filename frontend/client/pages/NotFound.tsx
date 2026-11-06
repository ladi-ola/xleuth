import { useLocation, Link } from "react-router-dom";
import { useEffect } from "react";
import { Layout } from "@/components/xleuth/Layout";
import { usePageMeta } from "@/hooks/use-page-meta";

// Task 13: branded 404 inside the app shell (dark theme, primary CTA home).
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
    <Layout width="md">
      <div className="flex flex-col items-center gap-4 px-4 py-16 text-center md:px-0 md:py-24">
        <span className="text-4xl font-bold text-foreground">404</span>
        <p className="text-sm text-foreground/80">
          {slug
            ? `Unknown basket "${slug}". It may have expired, been renamed, or never existed.`
            : "This page does not exist."}
        </p>
        <div className="flex gap-3">
          <Link
            to="/app"
            className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground"
          >
            Launch app
          </Link>
          <Link
            to="/explore"
            className="rounded-lg border-[0.4px] border-border px-4 py-2 text-sm text-foreground"
          >
            Browse baskets
          </Link>
        </div>
      </div>
    </Layout>
  );
};

export default NotFound;
