import { useEffect, useRef, useState } from "react";
import { auth } from "../lib/api";

export function useWebSocket(submissionId?: string) {
  const [event, setEvent] = useState<Record<string, unknown> | null>(null);
  const [connected, setConnected] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  useEffect(() => {
    if (!submissionId || !auth.token()) return;
    const base = (import.meta.env.VITE_WS_BASE ?? "ws://localhost:8000/v1").replace(/\/$/, "");
    const ws = new WebSocket(`${base}/ws/${submissionId}?token=${encodeURIComponent(auth.token()!)}`);
    socket.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = message => { try { setEvent(JSON.parse(message.data)); } catch { setEvent({ event: "raw", data: message.data }); } };
    return () => ws.close();
  }, [submissionId]);
  return { event, connected, close: () => socket.current?.close() };
}
