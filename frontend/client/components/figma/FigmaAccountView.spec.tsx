import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FigmaAccountView } from "./FigmaAccountView";

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }) }));

describe("Figma account presentation", () => {
  it("keeps signed-in actions but does not invent a missing balance", () => {
    const markup = renderToStaticMarkup(<FigmaAccountView
      signedIn displayName="Test User" initials="TU" address="0x12345678"
      shortAddress="0x1234...5678" balance={undefined} isClaiming={false}
      onSignIn={vi.fn()} onSignOut={vi.fn()} onClaim={vi.fn()} onCopyAddress={vi.fn()}
    />);
    expect(markup).toContain("Test User");
    expect(markup).toContain("Copy address");
    expect(markup).toContain("Claim test tokens");
    expect(markup).toContain("Sign out");
    expect(markup).toContain("—");
    expect(markup).not.toContain("$0.00");
    expect(markup).not.toContain("alex@example.com");
  });
});
