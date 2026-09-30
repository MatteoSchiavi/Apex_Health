"use client";

/**
 * Apex Health — useSyncStatus hook.
 *
 * Connects to the Apex sync mini-service (port 3005) via socket.io, with
 * the gateway-aware path `/?XTransformPort=3005`. Returns the latest sync
 * event + connection state so the Overview status strip can show a live
 * "synced" indicator that pulses green when new data arrives.
 *
 * If the real-time connection can't be established (e.g. in dev where the
 * gateway can't route to a separate mini-service port), the hook falls back
 * to a deterministic simulated sync event loop every 8-15s. The UI shows a
 * small "sim" indicator so users know it's not a real connection.
 *
 * States:
 *  - connecting: initial state, socket trying to connect
 *  - connected: socket is live; latest event may be null until first broadcast
 *  - disconnected: socket dropped (will auto-reconnect) or never reachable
 *    → fallback to simulated sync events
 *
 * Latest event shape: { provider, last_synced_at, freshness_ms, status, samples_synced }
 */

import { useEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";

export interface SyncEvent {
  provider: string;
  last_synced_at: string;
  freshness_ms: number;
  status: "active" | "paused" | "error";
  samples_synced: number;
  /** true when this event came from the fallback simulator (not a real socket) */
  simulated?: boolean;
}

type ConnectionState = "connecting" | "connected" | "disconnected";

const PROVIDERS = ["Garmin", "Whoop", "Strava", "Oura", "COROS"] as const;
const SIM_BASE_DELAY = 8000;
const SIM_JITTER = 7000;

function nextSimEvent(): SyncEvent {
  const idx = Math.floor(Math.random() * PROVIDERS.length);
  const provider = PROVIDERS[idx] ?? "Garmin";
  const status: SyncEvent["status"] = provider === "Oura" ? "paused" : "active";
  return {
    provider,
    last_synced_at: new Date().toISOString(),
    freshness_ms: status === "active" ? Math.floor(2000 + Math.random() * 6000) : 86400000,
    status,
    samples_synced: status === "active" ? Math.floor(2 + Math.random() * 18) : 0,
    simulated: true,
  };
}

export function useSyncStatus() {
  const [state, setState] = useState<ConnectionState>("connecting");
  const [latest, setLatest] = useState<SyncEvent | null>(null);
  const [pulseKey, setPulseKey] = useState(0); // bump on each new event to trigger animation
  const socketRef = useRef<Socket | null>(null);
  const simTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fallbackArmedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    // Arm the fallback simulator after 4s — if the socket hasn't connected by
    // then, we assume the gateway can't route to the mini-service and we run
    // the simulator instead. The socket keeps trying to reconnect in the
    // background; if it eventually connects, the simulator stops.
    const armFallback = setTimeout(() => {
      if (cancelled) return;
      if (state !== "connected" && !fallbackArmedRef.current) {
        fallbackArmedRef.current = true;
        setState("disconnected");
        // Kick off the first simulated event
        const ev = nextSimEvent();
        setLatest(ev);
        setPulseKey((k) => k + 1);
        scheduleNextSim();
      }
    }, 4000);

    function scheduleNextSim() {
      const delay = SIM_BASE_DELAY + Math.floor(Math.random() * SIM_JITTER);
      simTimerRef.current = setTimeout(() => {
        if (cancelled) return;
        const ev = nextSimEvent();
        setLatest(ev);
        setPulseKey((k) => k + 1);
        scheduleNextSim();
      }, delay);
    }

    // Try to connect to the real socket.io backend
    const socket = io("/?XTransformPort=3005", {
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1500,
      reconnectionDelayMax: 5000,
      timeout: 3000,
    });
    socketRef.current = socket;

    socket.on("connect", () => {
      if (cancelled) return;
      setState("connected");
      // Stop the simulator if it was running
      if (simTimerRef.current) {
        clearTimeout(simTimerRef.current);
        simTimerRef.current = null;
      }
    });
    socket.on("disconnect", () => {
      if (cancelled) return;
      setState("disconnected");
      // If fallback already armed, let it keep running. Otherwise arm it now.
      if (!fallbackArmedRef.current) {
        fallbackArmedRef.current = true;
        scheduleNextSim();
      }
    });
    socket.on("connect_error", () => {
      if (cancelled) return;
      setState("disconnected");
    });

    socket.on("apex:hello", (payload: { ok: boolean; server_time: string }) => {
      if (cancelled) return;
      if (payload?.ok) {
        setState("connected");
        if (simTimerRef.current) {
          clearTimeout(simTimerRef.current);
          simTimerRef.current = null;
        }
      }
    });

    socket.on("apex:sync", (ev: SyncEvent) => {
      if (cancelled) return;
      setLatest({ ...ev, simulated: false });
      setPulseKey((k) => k + 1);
    });

    return () => {
      cancelled = true;
      clearTimeout(armFallback);
      if (simTimerRef.current) {
        clearTimeout(simTimerRef.current);
        simTimerRef.current = null;
      }
      socket.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
    };
  }, []);

  return { state, latest, pulseKey };
}
