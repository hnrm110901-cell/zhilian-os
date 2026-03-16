import { useEffect, useRef, useCallback, useState } from 'react';

export interface WsMessage {
  type: string;
  [key: string]: unknown;
}

interface UseWebSocketOptions {
  onMessage?: (msg: WsMessage) => void;
  reconnectDelay?: number;
  maxRetries?: number;
}

export function useWebSocket(url: string | null, options: UseWebSocketOptions = {}) {
  const { onMessage, reconnectDelay = 3000, maxRetries = 10 } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<() => void>();
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!url) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        onMessage?.(msg);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (retriesRef.current < maxRetries) {
        retriesRef.current += 1;
        timerRef.current = setTimeout(() => { connectRef.current?.(); }, reconnectDelay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url, onMessage, reconnectDelay, maxRetries]);

  // Keep connectRef in sync with the latest connect callback
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
