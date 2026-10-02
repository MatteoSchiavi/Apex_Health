"use client";

/**
 * Garmin Connect form — lets the user enter their Garmin credentials from the
 * Settings page. Validates by attempting a login, then stores in the
 * Integration table (via POST /api/garmin/connect) so future syncs use them.
 *
 * If already connected, shows the connected email + a Disconnect button.
 * If not, shows email + password fields + a Connect button.
 */

import { useEffect, useState } from "react";
import { Loader2, RefreshCw, CheckCircle2, AlertCircle, Eye, EyeOff, Unlink } from "lucide-react";
import { ApexButton, Hairline, Badge } from "@/components/apex/kit";
import { useToast } from "@/hooks/use-toast";

export function GarminConnectForm({ onConnected }: { onConnected: () => void }) {
  const { toast } = useToast();
  const [connected, setConnected] = useState(false);
  const [connectedEmail, setConnectedEmail] = useState<string | null>(null);
  const [lastSynced, setLastSynced] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  // Fetch connection status on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/garmin/connect", { cache: "no-store" });
        const j = await r.json();
        if (cancelled) return;
        if (j?.ok) {
          setConnected(j.connected);
          setConnectedEmail(j.email);
          setLastSynced(j.lastSyncedAt);
          if (j.email && !email) setEmail(j.email);
        }
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    setError(null);
    try {
      const r = await fetch("/api/garmin/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const j = await r.json();
      if (j?.ok) {
        setConnected(true);
        setConnectedEmail(email);
        toast({ title: "Garmin connected", description: `Credentials validated for ${email}` });
        setPassword(""); // clear the password field for security
        onConnected();
        // Auto-sync immediately after connecting
        await handleSync();
      } else {
        setError(j?.error || "Connection failed");
        toast({ title: "Connection failed", description: j?.error, variant: "destructive" });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Network error";
      setError(msg);
      toast({ title: "Connection failed", description: msg, variant: "destructive" });
    } finally {
      setConnecting(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const r = await fetch("/api/garmin/sync", { method: "POST" });
      const j = await r.json();
      if (j?.ok) {
        const { activities, sleepSessions, dailyStats } = j.report;
        if (j.report.errors?.length > 0) {
          toast({ title: "Sync completed with errors", description: j.report.errors[0], variant: "destructive" });
        } else {
          toast({
            title: "Sync complete",
            description: `${activities} activities · ${sleepSessions} sleep sessions · ${dailyStats} daily stats`,
          });
          setLastSynced(new Date().toISOString());
        }
      } else {
        toast({ title: "Sync failed", description: j?.error, variant: "destructive" });
      }
    } catch (e) {
      toast({ title: "Sync failed", description: e instanceof Error ? e.message : "unknown", variant: "destructive" });
    } finally {
      setSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      const r = await fetch("/api/garmin/connect", { method: "DELETE" });
      const j = await r.json();
      if (j?.ok) {
        setConnected(false);
        setConnectedEmail(null);
        setPassword("");
        toast({ title: "Garmin disconnected" });
      }
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="border-t border-hairline">
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="text-[14px] font-medium text-ink2">Garmin Connect</div>
            {loading ? (
              <Loader2 size={12} className="animate-spin text-faint" />
            ) : connected ? (
              <Badge tone="positive" dot>Connected</Badge>
            ) : (
              <Badge tone="neutral" dot>Not connected</Badge>
            )}
          </div>
          {connected && (
            <ApexButton
              variant="secondary"
              size="sm"
              onClick={handleSync}
              disabled={syncing}
              icon={syncing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            >
              {syncing ? "Syncing…" : "Sync now"}
            </ApexButton>
          )}
        </div>

        {loading ? null : connected ? (
          /* Connected state */
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <CheckCircle2 size={14} className="text-positiveText" />
              <span className="font-medium text-ink2">{connectedEmail}</span>
              {lastSynced && (
                <>
                  <span className="text-faint">·</span>
                  <span className="text-faint">Last synced {new Date(lastSynced).toLocaleString()}</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <ApexButton
                variant="ghost"
                size="sm"
                icon={<Unlink size={13} />}
                onClick={handleDisconnect}
              >
                Disconnect
              </ApexButton>
            </div>
            <p className="text-[12px] text-faint">
              {/* TODO i18n */}
              Your credentials are stored in the local database and used for
              scheduled syncs. Disconnect to clear them.
            </p>
          </div>
        ) : (
          /* Not connected — show the form */
          <div className="space-y-3">
            {error && (
              <div className="flex items-start gap-2 rounded-[var(--radius-control)] border border-alert/40 bg-alertSoft/40 px-2.5 py-2 text-[12px] text-alertText">
                <AlertCircle size={13} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
            <div>
              <label className="mb-1 block text-[14px] font-medium text-ink2">Garmin email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                className="num h-9 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 text-[12px] text-ink placeholder:text-faint focus:border-primary/60 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-[14px] font-medium text-ink2">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && email && password && !connecting) {
                      handleConnect();
                    }
                  }}
                  className="num h-9 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 pr-9 text-[12px] text-ink placeholder:text-faint focus:border-primary/60 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-faint transition-colors hover:text-ink"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ApexButton
                variant="primary"
                size="md"
                onClick={handleConnect}
                disabled={!email || !password || connecting}
                icon={connecting ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
              >
                {connecting ? "Connecting…" : "Connect & sync"}
              </ApexButton>
              <span className="text-[12px] text-faint">
                {/* TODO i18n */}
                Credentials are validated by logging in to Garmin Connect, then
                stored locally for future syncs.
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
