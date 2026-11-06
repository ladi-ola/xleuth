import { useEffect } from "react";

// Task 6: per-page title/description/canonical/social tags.
//
// Honest limitation: this app is a client-rendered SPA served with a 200
// rewrite, so crawlers WITHOUT JS execution only see index.html's static
// tags. These JS tags improve tabs, history, link unfurls in JS-capable
// clients and real browsers. If crawler-visible per-page tags are needed,
// add prerendering/SSR for public routes (see docs/programmatic-seo.md).
// Vercel sends noindex for non-root routes; App.tsx keeps the DOM robots tag
// in sync during client-side navigation.

const SITE_URL: string = import.meta.env.VITE_PUBLIC_SITE_URL || "";

function upsertMeta(attr: "name" | "property", key: string, content: string): void {
  if (!content) return;
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel: string, href: string): void {
  if (!href) return;
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

export function usePageMeta(opts: {
  title: string;
  description: string;
  path: string;
  image?: string;
}): void {
  useEffect(() => {
    document.title = opts.title;
    upsertMeta("name", "description", opts.description);
    if (SITE_URL) {
      const url = SITE_URL.replace(/\/$/, "") + opts.path;
      upsertLink("canonical", url);
      upsertMeta("property", "og:url", url);
      upsertMeta("property", "og:title", opts.title);
      upsertMeta("property", "og:description", opts.description);
      upsertMeta("property", "og:image", `${SITE_URL.replace(/\/$/, "")}${opts.image ?? "/og-image.png"}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.title, opts.description, opts.path]);
}
