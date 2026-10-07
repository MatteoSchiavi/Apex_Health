/**
 * Settings — personalization + account management hub (owner spec: "a good
 * settings page where personalization and settings management are easy").
 *
 * Sections: Profile · Appearance (theme/language/units — the account prefs
 * from migration 0007, applied instantly via the ui store) · Devices &
 * Services (the main-device priority law) · Security (password + the
 * local-data note) · Owner-only: invites + role/AI-tier.
 *
 * Provider names stay untranslated (brand names); everything else rides the
 * locale files. Language changes apply the instant the segment is clicked.
 */

import { Fragment, type FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Tabs } from "../../components/Tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Copy, ExternalLink, Plus, Trash2 } from "lucide-react";
import { api, type DeviceOut, type Me } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import DataHealthPage from "../lab/DataHealthPage";
import { NotificationPreferences } from "../lab/NotificationsPage";
import { InstallApp } from "../pwa/InstallApp";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Input,
  Loading,
  PageHeader,
  Segmented,
  Select,
} from "../../components/kit";

/* ------------------------------------------------------------------ profile */

function ProfileSection({ me }: { me: Me }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState(me.name);
  const [dob, setDob] = useState(me.dob ?? "");
  const [sex, setSex] = useState(me.sex ?? "");
  const [height, setHeight] = useState(
    me.height_cm ? String(me.height_cm) : "",
  );
  const [timezone, setTimezone] = useState(me.timezone);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (saved) {
      const id = setTimeout(() => setSaved(false), 2500);
      return () => clearTimeout(id);
    }
  }, [saved]);

  const save = useMutation({
    mutationFn: () =>
      api.put<Me>("/me", {
        name,
        dob: dob || null,
        sex: sex || null,
        height_cm: height ? Number(height) : null,
        timezone,
      }),
    onSuccess: (next) => {
      useUi.getState().setMe({ ...me, ...next });
      setSaved(true);
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });

  return (
    <Card>
      <CardHeader
        title={t("settings.profile")}
        right={
          saved ? (
            <Badge tone="positive">{t("settings.saved")}</Badge>
          ) : undefined
        }
      />
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
        className="grid grid-cols-1 gap-3 md:grid-cols-2"
      >
        <Input
          label={t("settings.name")}
          value={name}
          onChange={setName}
          required
        />
        <Input
          label={t("settings.dob")}
          value={dob}
          onChange={setDob}
          type="date"
        />
        <Select
          label={t("settings.sex")}
          value={sex}
          onChange={setSex}
          options={[
            { value: "", label: t("design.not_specified") },
            { value: "male", label: t("settings.male") },
            { value: "female", label: t("settings.female") },
            { value: "other", label: t("settings.other") },
          ]}
        />
        <Input
          label={t("settings.height")}
          value={height}
          onChange={setHeight}
          type="number"
          min={120}
          max={230}
        />
        <Input
          label={t("settings.timezone")}
          value={timezone}
          onChange={setTimezone}
          placeholder="Europe/Rome"
          className="md:col-span-2"
        />
        <div className="md:col-span-2">
          <Button type="submit" disabled={save.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </form>
      {save.isError && (
        <div className="mt-3">
          <ErrorNote />
        </div>
      )}
    </Card>
  );
}

/* --------------------------------------------------------------- appearance */

function AppearanceSection() {
  const { t } = useTranslation();
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const locale = useUi((s) => s.locale);
  const setLocale = useUi((s) => s.setLocale);
  const me = useUi((s) => s.me);

  const preferenceSaving = useUi((s) => s.preferenceSaving);
  const qc = useQueryClient();
  const saveUnits = useMutation({
    mutationFn: (units: "metric" | "imperial") => api.put<Me>("/me", { units }),
    onMutate: () =>
      useUi.setState({ preferenceSaving: true, preferenceError: false }),
    onSuccess: (next) => {
      useUi.getState().setMe(next);
      qc.setQueryData(["me"], next);
    },
    onSettled: () => useUi.setState({ preferenceSaving: false }),
  });
  const units = me?.units ?? "metric";

  return (
    <Card>
      <CardHeader
        eyebrow={t("settings.title")}
        title={t("settings.theme_section")}
      />
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink2">{t("theme.protocol")}</span>
          <Segmented
            disabled={preferenceSaving}
            value={theme}
            onChange={(v) => setTheme(v)}
            options={[
              { value: "dark", label: t("theme.dark") },
              { value: "light", label: t("theme.light") },
            ]}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink2">
            {t("settings.language")}
          </span>
          <Segmented
            disabled={preferenceSaving}
            value={locale}
            onChange={(v) => setLocale(v)}
            options={[
              { value: "en", label: "English" },
              { value: "it", label: "Italiano" },
            ]}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink2">{t("settings.units")}</span>
          <Segmented
            disabled={preferenceSaving}
            value={units}
            onChange={(v) => saveUnits.mutate(v)}
            options={[
              { value: "metric", label: t("settings.metric") },
              { value: "imperial", label: t("settings.imperial") },
            ]}
          />
        </div>
      </div>
      {saveUnits.isError && <ErrorNote />}
    </Card>
  );
}

/* ------------------------------------------------------------------ devices */

const PROVIDERS: { key: string; name: string; connectable: boolean }[] = [
  { key: "garmin", name: "Garmin Connect", connectable: true },
  { key: "technogym", name: "Technogym", connectable: true },
  { key: "whoop", name: "Whoop", connectable: true },
  { key: "strava", name: "Strava", connectable: true },
  { key: "oura", name: "Oura", connectable: true },
  { key: "coros", name: "COROS · MCP", connectable: true },
];

/**
 * Garmin credentials flow — the UI answer to "how do I link my Garmin
 * account?": POST /settings/integrations/garmin/connect with the account
 * email/password (MFA step handled inline). Only the session tokens are
 * stored server-side, app-layer-encrypted; the password never leaves this
 * request. After a successful connect the full-history backfill task is
 * enqueued and the row flips to CONNECTED.
 */
function GarminConnectForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaStep, setMfaStep] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = useMutation({
    mutationFn: () =>
      api.post<{ connected: boolean; mfa_required: boolean }>(
        "/settings/integrations/garmin/connect",
        mfaStep ? { email, password, mfa_code: mfaCode } : { email, password },
      ),
    onSuccess: (res) => {
      if (res.mfa_required) {
        setMfaStep(true);
        setError(null);
        return;
      }
      setPassword("");
      setMfaCode("");
      setMfaStep(false);
      onDone();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : String(err)),
  });

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        connect.mutate();
      }}
      className="mt-2 bg-surface2 p-3"
    >
      <p className="mb-3 text-[12px] leading-relaxed text-muted">
        {t("settings.garmin_connect_hint")}
      </p>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Input
          label={t("settings.garmin_email")}
          value={email}
          onChange={setEmail}
          type="email"
          autoComplete="off"
          required
        />
        <Input
          label={t("settings.garmin_password")}
          value={password}
          onChange={setPassword}
          type="password"
          autoComplete="off"
          required
        />
        {mfaStep && (
          <Input
            label={t("settings.garmin_mfa")}
            value={mfaCode}
            onChange={setMfaCode}
            placeholder="123456"
            required
          />
        )}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Button type="submit" disabled={connect.isPending}>
          {connect.isPending
            ? t("settings.connecting")
            : mfaStep
              ? t("settings.verify_code")
              : t("settings.connect")}
        </Button>
        {mfaStep && (
          <span className="text-[12px] text-warningText">
            {t("settings.mfa_sent")}
          </span>
        )}
      </div>
      {error && (
        <div className="mt-2">
          <ErrorNote message={error} />
        </div>
      )}
    </form>
  );
}

function CorosConnectForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const [token, setToken] = useState("");
  const status = useQuery({
    queryKey: ["coros-mcp-status"],
    queryFn: () => api.get<{ configured: boolean }>("/settings/integrations/coros/mcp/status"),
  });
  const connect = useMutation({
    mutationFn: () => api.post("/settings/integrations/coros/mcp/connect", { access_token: token }),
    onSuccess: () => { setToken(""); onDone(); },
  });
  return <form className="border-b border-hairline py-5" onSubmit={(event) => { event.preventDefault(); connect.mutate(); }}>
    <p className="mb-3 text-[12px] text-muted">{t("refinement.coros_mcp_note")}</p>
    {status.isLoading ? <Loading /> : status.isError ? <ErrorNote /> : !status.data?.configured ? <p className="text-[13px] text-muted">{t("refinement.coros_mcp_setup")}</p> : <div className="flex flex-wrap items-end gap-3">
      <Input label={t("refinement.coros_mcp_token")} value={token} onChange={setToken} type="password" required autoComplete="off" />
      <Button type="submit" disabled={connect.isPending || !token.trim()}>{t("settings.connect")}</Button>
    </div>}
    {connect.isError && <div className="mt-3"><ErrorNote message={connect.error.message} /></div>}
  </form>;
}

function DevicesSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<DeviceOut[]>("/settings/devices"),
  });
  const maturity = useQuery({
    queryKey: ["provider-support"],
    queryFn: () => api.get<Record<string, NonNullable<DeviceOut["support"]>>>("/settings/devices/support"),
    staleTime: 300_000,
  });
  const [flowError, setFlowError] = useState<string | null>(null);
  const [garminOpen, setGarminOpen] = useState(false);
  const [corosOpen, setCorosOpen] = useState(false);

  const setMain = useMutation({
    mutationFn: (integration_id: number | null) =>
      api.put<DeviceOut[]>("/settings/devices/main", { integration_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });

  const disconnect = useMutation({
    mutationFn: (provider: string) =>
      api.delete<{ provider: string; disconnected: boolean }>(
        `/settings/integrations/${provider}`,
      ),
    onSuccess: () => {
      setFlowError(null);
      qc.invalidateQueries({ queryKey: ["devices"] });
    },
    onError: (err) =>
      setFlowError(err instanceof Error ? err.message : String(err)),
  });

  const connect = useMutation({
    mutationFn: (provider: string) =>
      api.post<{ authorize_url: string }>(
        `/settings/integrations/${provider}/authorize`,
      ),
    onSuccess: ({ authorize_url }) => {
      setFlowError(null);
      window.location.assign(authorize_url);
    },
    onError: (err) =>
      setFlowError(err instanceof Error ? err.message : String(err)),
  });

  const [job, setJob] = useState<string | null>(() => {
    try {
      return localStorage.getItem("apex.sync." + useUi.getState().me?.user_id);
    } catch {
      return null;
    }
  });
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const syncStatus = useQuery({
    queryKey: ["sync-status", job],
    queryFn: () =>
      api.get<{
        state: string;
        completed: boolean;
        result?: { status: string };
        error?: string;
      }>("/settings/integrations/garmin/sync/" + job),
    enabled: !!job,
    refetchInterval: (query) =>
      query.state.data?.completed || query.state.status === "error"
        ? false
        : 2000,
    retry: false,
  });
  const syncNow = useMutation({
    mutationFn: (provider: string) =>
      api.post<{ job_id: string; enqueued: boolean; completed: boolean }>(
        `/settings/integrations/${provider}/sync`,
      ),
    onSuccess: (res) => {
      setJob(res.job_id);
      setSyncMessage(t("design.sync_queued"));
      setFlowError(null);
    },
    onError: (err) => setFlowError(err.message),
  });
  useEffect(() => {
    try {
      const key = "apex.sync." + useUi.getState().me?.user_id;
      if (job) localStorage.setItem(key, job);
      else localStorage.removeItem(key);
    } catch {
      /* unavailable */
    }
  }, [job]);
  useEffect(() => {
    const result = syncStatus.data;
    if (!result?.completed) return;
    if (result.state === "SUCCESS" && result.result?.status === "ok")
      setSyncMessage(t("design.sync_done"));
    else if (result.state === "SUCCESS" && result.result?.status === "partial")
      setSyncMessage(t("design.sync_partial"));
    else {
      setSyncMessage(null);
      setFlowError(result.error ?? t("design.sync_failed"));
    }
    // A completed job makes fresh data available; queued work does not.
    for (const key of [
      "devices",
      "overview",
      "sleep",
      "sleep-stages",
      "activities",
      "activity",
      "streams",
      "metric",
    ])
      qc.invalidateQueries({ queryKey: [key] });
    setJob(null);
  }, [syncStatus.data, qc, t]);
  useEffect(() => {
    if (syncStatus.isError) {
      setFlowError(t("design.sync_status_failed"));
      setJob(null);
      setSyncMessage(null);
    }
  }, [syncStatus.isError, t]);

  const byProvider = new Map((devices.data ?? []).map((d) => [d.provider, d]));
  const garminConnected = byProvider.get("garmin")?.status === "active";

  return (
    <Card>
      <CardHeader
        title={t("settings.devices")}
        right={
          devices.isLoading ? undefined : (
            <span className="num text-[12px] text-muted">
              {devices.data?.length ?? 0}
            </span>
          )
        }
      />
      <p className="mb-3 text-[12px] leading-relaxed text-muted">
        {t("settings.main_device_hint")}
      </p>
      {devices.isLoading ? (
        <Loading />
      ) : (
        <div className="flex flex-col">
          {PROVIDERS.map(({ key, name }) => {
            const d = byProvider.get(key);
            const support = d?.support ?? maturity.data?.[key];
            const connected = d?.status === "active";
            return (
              <Fragment key={key}>
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline py-5 last:border-0">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium text-ink">
                        {name}
                      </span>
                      {support && <Badge tone="warning">{t("providerSupport." + support.status)}</Badge>}
                      {d?.is_main && (
                        <Badge tone="primary">
                          {t("settings.main_device")}
                        </Badge>
                      )}
                      {connected ? (
                        <Badge tone="positive">{t("settings.connected")}</Badge>
                      ) : d ? (
                        <Badge tone="warning">
                          {d.status === "revoked"
                            ? t("settings.disconnected")
                            : d.status}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="num mt-0.5 text-[12px] text-muted">
                      {connected
                        ? `${t("settings.connected")} · ${
                            d?.last_synced_at
                              ? new Date(d.last_synced_at).toLocaleString()
                              : t("settings.never")
                          }`
                        : key === "garmin"
                          ? t("settings.garmin_not_connected")
                          : t("settings.provider_setup")}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {connected && !d?.is_main && (
                      <Button
                        variant="ghost"
                        disabled={setMain.isPending}
                        onClick={() => d && setMain.mutate(d.integration_id)}
                      >
                        {t("settings.set_main")}
                      </Button>
                    )}
                    {connected && (
                      <Button
                        variant="ghost"
                        disabled={disconnect.isPending}
                        onClick={() => disconnect.mutate(key)}
                      >
                        {t("settings.disconnect")}
                      </Button>
                    )}
                    {connected && (
                      <Button
                        variant="ghost"
                        disabled={syncNow.isPending || !!job}
                        onClick={() => syncNow.mutate(key)}
                      >
                        {job
                          ? t("design.sync_running")
                          : t("settings.sync_now")}
                      </Button>
                    )}
                    {key === "garmin" && !connected && (
                      <Button
                        variant={garminOpen ? "ghost" : "primary"}
                        onClick={() => setGarminOpen((v) => !v)}
                      >
                        {garminOpen ? t("common.close") : t("settings.connect")}
                      </Button>
                    )}
                    {key === "coros" && !connected && <Button variant="ghost" onClick={() => setCorosOpen((value) => !value)}>{corosOpen ? t("common.close") : t("settings.connect")}</Button>}
                    {key !== "garmin" && key !== "coros" && !connected && (
                      <Button
                        variant="ghost"
                        disabled={connect.isPending}
                        onClick={() => connect.mutate(key)}
                        icon={<ExternalLink size={12} />}
                      >
                        {t("settings.connect")}
                      </Button>
                    )}
                  </div>
                </div>
                {key === "garmin" && garminOpen && !garminConnected ? (
                  <GarminConnectForm
                    onDone={() => {
                      setGarminOpen(false);
                      qc.invalidateQueries({ queryKey: ["devices"] });
                    }}
                  />
                ) : null}
                {key === "coros" && corosOpen && !connected && <CorosConnectForm onDone={() => { setCorosOpen(false); qc.invalidateQueries({ queryKey: ["devices"] }); }} />}
              </Fragment>
            );
          })}
        </div>
      )}
      {syncMessage && (
        <p role="status" className="mt-4 text-[13px] text-muted">
          {syncMessage}
        </p>
      )}
      {setMain.isError && <ErrorNote />}
      {devices.isError && <ErrorNote />}
      {flowError && (
        <div className="mt-3">
          <ErrorNote message={flowError} />
        </div>
      )}
      <p className="mt-4 border-t border-hairline pt-3 text-[12px] leading-relaxed text-faint">
        {t("settings.tokens_note")}
      </p>
    </Card>
  );
}

/* ----------------------------------------------------------------- security */

function SecuritySection() {
  const { t } = useTranslation();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [done, setDone] = useState(false);

  const change = useMutation({
    mutationFn: () =>
      api.put("/me/password", {
        current_password: current,
        new_password: next,
      }),
    onSuccess: () => {
      setDone(true);
      setCurrent("");
      setNext("");
    },
  });

  return (
    <Card>
      <CardHeader
        eyebrow={t("settings.account")}
        title={t("settings.password")}
      />
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          change.mutate();
        }}
        className="grid grid-cols-1 gap-3 md:grid-cols-2"
      >
        <Input
          label={t("settings.current_password")}
          value={current}
          onChange={setCurrent}
          type="password"
          required
        />
        <Input
          label={t("settings.new_password")}
          value={next}
          onChange={setNext}
          type="password"
          required
        />
        <div className="md:col-span-2">
          <Button type="submit" variant="ghost" disabled={change.isPending}>
            {done ? t("settings.password_changed") : t("settings.password")}
          </Button>
        </div>
      </form>
      {change.isError && (
        <div className="mt-3">
          <ErrorNote />
        </div>
      )}
      <p className="mt-4 border-t border-hairline pt-3 text-[12px] leading-relaxed text-muted">
        {t("settings.data_local")}
      </p>
    </Card>
  );
}

/* ------------------------------------------------------------------ invites */

interface InviteRow {
  id: number;
  code: string;
  used_by: number | null;
  expired: boolean;
  expires_at: string;
}

function InviteCode({ code }: { code: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="mono inline-flex items-center gap-1.5 rounded-sm border border-hairline bg-surface2 px-2 py-1 text-[12px] text-ink2 hover:bg-surface3"
      onClick={() => {
        navigator.clipboard?.writeText(code).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          },
          () => undefined,
        );
      }}
      title={t("settings.copy")}
    >
      {copied ? (
        <Check size={11} className="text-positiveText" />
      ) : (
        <Copy size={11} />
      )}
      {code}
    </button>
  );
}

function InvitesSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const invites = useQuery({
    queryKey: ["invites"],
    queryFn: () => api.get<InviteRow[]>("/settings/invites"),
  });
  const mint = useMutation({
    mutationFn: () => api.post<InviteRow>("/settings/invites"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.delete(`/settings/invites/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });

  return (
    <Card>
      <CardHeader
        title={t("settings.invites")}
        right={
          <Button
            variant="ghost"
            className="!h-9 !px-2.5 text-[12px]"
            disabled={mint.isPending}
            onClick={() => mint.mutate()}
            icon={<Plus size={12} />}
          >
            {t("settings.mint_invite")}
          </Button>
        }
      />
      <p className="mb-3 text-[12px] leading-relaxed text-muted">
        {t("settings.invites_hint")}
      </p>
      {invites.isLoading ? (
        <Loading />
      ) : !invites.data || invites.data.length === 0 ? (
        <Empty>{t("settings.invites_hint")}</Empty>
      ) : (
        <div className="flex flex-col">
          {invites.data.map((inv) => (
            <div
              key={inv.id}
              className="flex items-center justify-between gap-3 border-b border-hairline py-2.5 last:border-0"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <InviteCode code={inv.code} />
                {inv.used_by ? (
                  <Badge tone="positive">{t("settings.invite_redeemed")}</Badge>
                ) : inv.expired ? (
                  <Badge tone="neutral">{t("settings.invite_expired")}</Badge>
                ) : (
                  <Badge tone="primary">{t("settings.invite_active")}</Badge>
                )}
                <span className="num text-[12px] text-muted">
                  {t("settings.expires")}{" "}
                  {new Date(inv.expires_at).toLocaleDateString()}
                </span>
              </div>
              {!inv.used_by && !inv.expired && (
                <button
                  type="button"
                  aria-label={t("settings.revoke")}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control text-muted hover:bg-alertSoft hover:text-alertText"
                  onClick={() => revoke.mutate(inv.id)}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {(revoke.isError || mint.isError || invites.isError) && (
        <div className="mt-3">
          <ErrorNote />
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ account */

function AccountSection() {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  if (!me) return null;
  return (
    <Card>
      <CardHeader eyebrow={t("settings.account")} title={me.email} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <div>
          <div className="eyebrow mb-1">{t("settings.role")}</div>
          <div className="text-[13px] font-medium text-ink">
            {me.role === "owner" ? t("settings.owner") : t("settings.friend")}
          </div>
        </div>
        <div>
          <div className="eyebrow mb-1">{t("settings.ai_tier")}</div>
          <div className="text-[13px] font-medium text-ink">
            {me.ai_access_tier}
          </div>
        </div>
        <div>
          <div className="eyebrow mb-1">{t("settings.email")}</div>
          <div className="text-[13px] font-medium text-ink truncate">
            {me.email}
          </div>
        </div>
      </div>
    </Card>
  );
}

/* --------------------------------------------------------------------- page */

export default function SettingsPage() {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  const [params, setParams] = useSearchParams();
  const options = [
    { value: "profile", label: t("settings.profile") },
    { value: "appearance", label: t("settings.theme_section") },
    { value: "devices", label: t("settings.devices") },
    { value: "notifications", label: t("lab.notification_preferences") },
    { value: "data-health", label: t("lab.data_health") },
    { value: "account", label: t("settings.account") },
    ...(me?.role === "owner"
      ? [{ value: "invites", label: t("settings.invites") }]
      : []),
  ];
  const tab = options.some((o) => o.value === params.get("tab"))
    ? params.get("tab")!
    : "profile";
  if (!me) return <Loading />;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("settings.title")}
        subtitle={t("settings.page_subtitle")}
      />
      <Tabs
        value={tab}
        onChange={(v) => setParams({ tab: v })}
        options={options}
        label={t("settings.title")}
      />
      <div className="max-w-4xl">
        {tab === "profile" && <ProfileSection me={me} />}
        {tab === "appearance" && <div className="flex flex-col gap-6"><AppearanceSection /><InstallApp /></div>}
        {tab === "devices" && <DevicesSection />}
        {tab === "notifications" && <NotificationPreferences />}
        {tab === "data-health" && <DataHealthPage embedded />}
        {tab === "account" && (
          <div className="flex flex-col gap-6">
            <AccountSection />
            <SecuritySection />
            <Card>
              <CardHeader title={t("navigation.data_and_legal")} />
              <div className="flex flex-col gap-3 text-[13px]">
                <Link className="text-link" to="/app/settings?tab=data-health">{t("lab.data_health")} · {t("navigation.export_erase")}</Link>
                <Link className="text-link" to="/legal/privacy">{t("legal.privacy_title")}</Link>
                <Link className="text-link" to="/legal/terms">{t("legal.terms_title")}</Link>
                <Link className="text-link" to="/legal/cookies">{t("legal.cookies_title")}</Link>
              </div>
            </Card>
          </div>
        )}
        {tab === "invites" && me.role === "owner" && <InvitesSection />}
      </div>
    </div>
  );
}
