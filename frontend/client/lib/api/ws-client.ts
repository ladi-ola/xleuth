import { secureUrl } from './urls';
// Reconnecting WebSocket client with exponential backoff

type MessageHandler = (data: unknown) => void;

interface WsClientOptions {
  url: string;
  protocols?: string | string[];
  onOpen?: () => void;
  onMessage?: MessageHandler;
  onError?: (error: Event) => void;
  onClose?: (event: CloseEvent) => void;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectInterval?: number;
  reconnectAttempts?: number;
}

type WsState = 'connecting' | 'open' | 'closing' | 'closed' | 'reconnecting';

export class ReconnectingWebSocket {
  private ws: WebSocket | null = null;
  protected options: Required<WsClientOptions>;
  private state: WsState = 'closed';
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private messageQueue: unknown[] = [];
  private subscribeMessage: unknown = null;

  constructor(options: WsClientOptions) {
    this.options = {
      url: options.url,
      protocols: options.protocols,
      onOpen: options.onOpen ?? (() => {}),
      onMessage: options.onMessage ?? (() => {}),
      onError: options.onError ?? (() => {}),
      onClose: options.onClose ?? (() => {}),
      reconnect: options.reconnect ?? true,
      reconnectInterval: options.reconnectInterval ?? 1000,
      maxReconnectInterval: options.maxReconnectInterval ?? 30000,
      reconnectAttempts: options.reconnectAttempts ?? Infinity,
    };
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.state = 'connecting';

    try {
      this.ws = new WebSocket(this.options.url, this.options.protocols);
      this.setupEventHandlers();
    } catch (error) {
      this.options.onError(error as Event);
      this.scheduleReconnect();
    }
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      this.state = 'open';
      this.reconnectAttempts = 0;
      this.options.onOpen();

      // Send queued messages
      this.messageQueue.forEach((msg) => this.send(msg));
      this.messageQueue = [];

      // Resend subscribe message if exists
      if (this.subscribeMessage) {
        this.send(this.subscribeMessage);
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.options.onMessage(data);
      } catch {
        // Ignore non-JSON messages
      }
    };

    this.ws.onerror = (error) => {
      this.options.onError(error);
    };

    this.ws.onclose = (event) => {
      this.state = 'closed';
      this.options.onClose(event);
      this.ws = null;

      if (this.options.reconnect && !event.wasClean) {
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.options.reconnectAttempts) {
      this.state = 'closed';
      return;
    }

    this.state = 'reconnecting';
    this.reconnectAttempts++;

    const delay = Math.min(
      this.options.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1),
      this.options.maxReconnectInterval
    );

    // Add jitter
    const jitter = delay * 0.1 * Math.random();
    const totalDelay = delay + jitter;

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, totalDelay);
  }

  send(data: unknown): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
      return true;
    }

    // Queue message for when connection opens
    this.messageQueue.push(data);
    return false;
  }

  subscribe(message: unknown): void {
    this.subscribeMessage = message;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.send(message);
    }
  }

  unsubscribe(): void {
    this.subscribeMessage = null;
  }

  close(): void {
    this.options.reconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, 'Client closed');
      this.ws = null;
    }
    this.state = 'closed';
  }

  getState(): WsState {
    return this.state;
  }

  isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // Allow external modification of message handler for React hook integration
  setOnMessage(handler: MessageHandler): void {
    this.options.onMessage = handler;
  }

  getOnMessage(): MessageHandler {
    return this.options.onMessage;
  }
}

// Specific WebSocket clients for price and orderbook

export interface PriceUpdateMessage {
  type: 'price_update';
  basket_name: string;
  index_price: number | null;
  scaled_price: number | null;
  timestamp: string;
}

export interface OrderBookSnapshotMessage {
  type: 'depth_snapshot';
  basket_name: string;
  bids: { price: number; size: number }[];
  asks: { price: number; size: number }[];
  best_bid: number | null;
  best_ask: number | null;
  mid_price: number | null;
  spread: number | null;
  ts: string;
}

export type BackendWsMessage = PriceUpdateMessage | OrderBookSnapshotMessage | { type: 'subscribe'; basket: string } | { type: 'ping' };

export function createPriceWsClient(
  basketName: string,
  onPriceUpdate: (data: PriceUpdateMessage) => void
): ReconnectingWebSocket {
  const wsUrl = `${secureUrl(import.meta.env.VITE_BACKEND_WS_URL || 'ws://localhost:8000')}/ws/price/${encodeURIComponent(basketName)}`;

  const client = new ReconnectingWebSocket({
    url: wsUrl,
    onMessage: (data) => {
      const msg = data as BackendWsMessage;
      if (msg.type === 'price_update') {
        onPriceUpdate(msg);
      }
    },
    onOpen: () => {
      client.subscribe({ type: 'subscribe', basket: basketName });
      // Start ping interval
      const pingInterval = setInterval(() => {
        if (client.isOpen()) {
          client.send({ type: 'ping' });
        } else {
          clearInterval(pingInterval);
        }
      }, 15000);
    },
    reconnect: true,
    reconnectInterval: 1000,
    maxReconnectInterval: 30000,
  });

  return client;
}

export function createOrderBookWsClient(
  basketName: string,
  onOrderBookUpdate: (data: OrderBookSnapshotMessage) => void
): ReconnectingWebSocket {
  const wsUrl = `${secureUrl(import.meta.env.VITE_BACKEND_WS_URL || 'ws://localhost:8000')}/ws/orderbook/${encodeURIComponent(basketName)}`;

  const client = new ReconnectingWebSocket({
    url: wsUrl,
    onMessage: (data) => {
      const msg = data as BackendWsMessage;
      if (msg.type === 'depth_snapshot') {
        onOrderBookUpdate(msg);
      }
    },
    onOpen: () => {
      client.subscribe({ type: 'subscribe', basket: basketName });
      const pingInterval = setInterval(() => {
        if (client.isOpen()) {
          client.send({ type: 'ping' });
        } else {
          clearInterval(pingInterval);
        }
      }, 15000);
    },
    reconnect: true,
    reconnectInterval: 1000,
    maxReconnectInterval: 30000,
  });

  return client;
}

// React hook for WebSocket lifecycle management
import { useEffect, useRef, useCallback } from 'react';

export function useWebSocket<T>(
  createClient: () => ReconnectingWebSocket,
  onMessage: (data: T) => void,
  deps: unknown[] = []
) {
  const clientRef = useRef<ReconnectingWebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    const client = createClient();
    clientRef.current = client;

    // Wrap onMessage to use current ref
    const originalOnMessage = client.getOnMessage();
    client.setOnMessage((data) => {
      onMessageRef.current(data as T);
      originalOnMessage(data);
    });

    client.connect();

    return () => {
      client.close();
      clientRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const send = useCallback((data: unknown) => {
    return clientRef.current?.send(data) ?? false;
  }, []);

  const subscribe = useCallback((message: unknown) => {
    clientRef.current?.subscribe(message);
  }, []);

  const getState = useCallback(() => {
    return clientRef.current?.getState() ?? 'closed';
  }, []);

  return { send, subscribe, getState };
}