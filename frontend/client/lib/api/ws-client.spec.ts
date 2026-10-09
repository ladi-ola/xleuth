import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ReconnectingWebSocket, createPriceWsClient } from "./ws-client";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState = MockWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onclose: ((event: { wasClean: boolean }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ wasClean: true });
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  dropUnclean() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ wasClean: false });
  }

  message(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ReconnectingWebSocket", () => {
  it("subscribes on open and routes price updates", () => {
    const onPrice = vi.fn();
    const client = createPriceWsClient("TOP20-OCTOBER", onPrice);
    client.connect();
    expect(MockWebSocket.instances).toHaveLength(1);

    MockWebSocket.instances[0].open();
    expect(MockWebSocket.instances[0].sent).toContainEqual(
      JSON.stringify({ type: "subscribe", basket: "TOP20-OCTOBER" })
    );

    MockWebSocket.instances[0].message({ type: "price_update", index_price: 23.91 });
    expect(onPrice).toHaveBeenCalledWith({ type: "price_update", index_price: 23.91 });

    // Non-price messages are ignored by the price client.
    MockWebSocket.instances[0].message({ type: "depth_snapshot" });
    expect(onPrice).toHaveBeenCalledTimes(1);
    client.close();
  });

  it("reconnects with resubscribe after an unclean close", () => {
    const client = new ReconnectingWebSocket({ url: "ws://x", reconnectInterval: 1000 });
    client.connect();
    MockWebSocket.instances[0].open();
    MockWebSocket.instances[0].dropUnclean();
    expect(client.getState()).toBe("reconnecting");

    vi.advanceTimersByTime(2000);
    expect(MockWebSocket.instances).toHaveLength(2);
    client.close();
  });

  it("does not reconnect after a clean close()", () => {
    const client = new ReconnectingWebSocket({ url: "ws://x", reconnectInterval: 1000 });
    client.connect();
    MockWebSocket.instances[0].open();
    client.close();
    vi.advanceTimersByTime(10_000);
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("stops after the configured reconnect attempts", () => {
    const client = new ReconnectingWebSocket({
      url: "ws://x",
      reconnectInterval: 100,
      reconnectAttempts: 1,
    });
    client.connect();
    MockWebSocket.instances[0].dropUnclean();
    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances).toHaveLength(2);
    MockWebSocket.instances[1].dropUnclean();
    vi.advanceTimersByTime(10_000);
    expect(MockWebSocket.instances).toHaveLength(2);
    expect(client.getState()).toBe("closed");
    client.close();
  });
});
