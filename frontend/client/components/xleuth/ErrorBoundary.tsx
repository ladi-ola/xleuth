import { Component, type ReactNode } from "react";
import { Link } from "react-router-dom";

// Task 13: minimal error boundary → 500-style fallback instead of a blank
// screen on uncaught render errors. Static, no data fetching.
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: unknown): void {
    console.error("Uncaught render error:", error);
  }

  render(): ReactNode {
    if (this.state.failed) {
      return (
        <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 bg-neutral-950 px-4 text-center">
          <span className="text-4xl font-bold text-neutral-100">500</span>
          <p className="text-sm text-neutral-300">
            Something went wrong loading this screen. Your wallet and funds are unaffected.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => window.location.reload()}
              className="rounded-lg bg-primary px-4 py-2 text-sm text-white"
            >
              Reload
            </button>
            <Link
              to="/"
              onClick={() => this.setState({ failed: false })}
              className="rounded-lg border-[0.4px] border-neutral-600 px-4 py-2 text-sm text-neutral-200"
            >
              Launch app
            </Link>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
