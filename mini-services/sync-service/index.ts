/**
 * Apex Health — Real-time sync mini-service.
 *
 * A small socket.io server on port 3005 that periodically emits "sync events"
 * to all connected clients. The Overview status strip connects via the gateway
 * and shows a live "synced" indicator when events arrive.
 *
 * Events emitted:
 *  - "apex:sync" — payload: { provider, last_synced_at, freshness_ms, status }
 *  - "apex:hello" — sent on connect: { ok: true, server_time }
 *
 * The provider cycles through the configured devices (Garmin, Whoop, Strava,
 * Oura, COROS) to simulate the realistic device-polling cadence of the Apex
 * Health backend.
 */

import { createServer } from "http";
import { Server } from "socket.io";

const PORT = 3005;
const PROVIDERS = ["Garmin", "Whoop", "Strava", "Oura", "COROS"] as const;

interface SyncEvent {
  provider: string;
  last_synced_at: string;
  freshness_ms: number;
  status: "active" | "paused" | "error";
  samples_synced: number;
}

let connectionCount = 0;
let cycleIdx = 0;

function nextSyncEvent(): SyncEvent {
  const provider = PROVIDERS[cycleIdx % PROVIDERS.length]!;
  cycleIdx += 1;
  // Freshness ramps down (more stale) for paused/error providers
  const status: SyncEvent["status"] = provider === "Oura" ? "paused" : "active";
  const freshness_ms = status === "active" ? Math.floor(2000 + Math.random() * 6000) : 86400000;
  return {
    provider,
    last_synced_at: new Date().toISOString(),
    freshness_ms,
    status,
    samples_synced: status === "active" ? Math.floor(2 + Math.random() * 18) : 0,
  };
}

const httpServer = createServer();
const io = new Server(httpServer, {
  path: "/",
  cors: { origin: "*", methods: ["GET", "POST"] },
  pingTimeout: 60000,
  pingInterval: 25000,
});

io.on("connection", (socket) => {
  connectionCount += 1;
  console.log(`[sync-service] connected (now ${connectionCount} clients) — socket ${socket.id}`);

  // Hello handshake
  socket.emit("apex:hello", { ok: true, server_time: new Date().toISOString() });

  // Welcome event so the UI has something to show immediately
  socket.emit("apex:sync", nextSyncEvent());

  socket.on("disconnect", () => {
    connectionCount = Math.max(0, connectionCount - 1);
    console.log(`[sync-service] disconnected (now ${connectionCount} clients) — socket ${socket.id}`);
  });

  socket.on("error", (err: unknown) => {
    console.error(`[sync-service] socket error:`, err);
  });
});

// Broadcast a fresh sync event to ALL connected clients every 8-15s
let broadcastTimer: NodeJS.Timeout | null = null;
function scheduleNextBroadcast() {
  const delay = 8000 + Math.floor(Math.random() * 7000);
  broadcastTimer = setTimeout(() => {
    const ev = nextSyncEvent();
    io.emit("apex:sync", ev);
    console.log(`[sync-service] broadcasted ${ev.provider} sync (status=${ev.status})`);
    scheduleNextBroadcast();
  }, delay);
}
scheduleNextBroadcast();

httpServer.listen(PORT, () => {
  console.log(`[sync-service] Apex Health sync service listening on port ${PORT}`);
});

// Graceful shutdown
function shutdown(signal: string) {
  console.log(`[sync-service] received ${signal}, shutting down...`);
  if (broadcastTimer) clearTimeout(broadcastTimer);
  io.close(() => {
    httpServer.close(() => {
      console.log("[sync-service] closed");
      process.exit(0);
    });
  });
}
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
