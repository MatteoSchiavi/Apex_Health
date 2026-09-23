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

import { type FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Copy, ExternalLink, Plus, Trash2 } from "lucide-react";
import { api, type DeviceOut, type Me } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Input,
  Loading,
  Segmented,
  Select,
  fmtNum,
} from "../../components/kit";

/* ------------------------------------------------------------------ profile */

function ProfileSection({ me }: { me: Me }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState(me.name);
  const [dob, setDob] = useState(me.dob ?? "");
  const [sex, setSex] = useState(me.sex ?? "other");
  const [height, setHeight] = useState(me.height_cm ? String(me.height_cm) : "");
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
        sex,
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
        eyebrow={t("settings.title")}
        title={t("settings.profile")}
        right={saved ? <Badge tone="positive">{t("settings.saved")}</Badge> : undefined}
      />
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
        className="grid grid-cols-1 gap-3 md:grid-cols-2"
      >
        <Input label={t("settings.name")} value={name} onChange={setName} required />
        <Input label={t("settings.dob")} value={dob} onChange={setDob} type="date" />
        <Select
          label={t("settings.sex")}
          value={sex}
          onChange={setSex}
          options={[
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
      {save.isError && <div className="mt-3"><ErrorNote /></div>}
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

  const saveUnits = useMutation({
    mutationFn: (units: "metric" | "imperial") => api.put<Me>("/me", { units }),
    onSuccess: (next) => useUi.getState().setMe({ ...(me as Me), ...next }),
  });
  const units = me?.units ?? "metric";

  return (
    <Card>
      <CardHeader eyebrow={t("settings.title")} title={t("settings.theme_section")} />
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink2">{t("theme.protocol")}</span>
          <Segmented
            value={theme}
            onChange={(v) => setTheme(v)}
            options={[
              { value: "dark", label: t("theme.dark") },
              { value: "light", label: t("theme.light") },
            ]}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] text-ink2">{t("settings.language")}</span>
          <Segmented
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
            value={units}
            onChange={(v) => saveUnits.mutate(v)}
            options={[
              { value: "metric", label: t("settings.metric") },
              { value: "imperial", label: t("settings.imperial") },
            ]}
          />
        </div>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ devices */

const PROVIDERS: { key: string; name: string; connectable: boolean; note?: string }[] = [
  { key: "garmin", name: "Garmin Connect", connectable: false },
  { key: "whoop", name: "Whoop", connectable: true },
  { key: "strava", name: "Strava", connectable: true },
  { key: "oura", name: "Oura", connectable: true },
  { key: "coros", name: "COROS", connectable: true },
];

function DevicesSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<DeviceOut[]>("/settings/devices"),
  });
  const [flowError, setFlowError] = useState<string | null>(null);

  const setMain = useMutation({
    mutationFn: (integration_id: number | null) =>
      api.put<DeviceOut[]>("/settings/devices/main", { integration_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["devices"] }),
  });

  const connect = useMutation({
    mutationFn: (provider: string) =>
      api.post<{ authorize_url: string }>(`/settings/integrations/${provider}/authorize`),
    onSuccess: ({ authorize_url }) => {
      setFlowError(null);
      window.open(authorize_url, "_blank", "noopener");
    },
    onError: (err) => setFlowError(err instanceof Error ? err.message : String(err)),
  });

  const byProvider = new Map((devices.data ?? []).map((d) => [d.provider, d]));

  return (
    <Card>
      <CardHeader
        eyebrow={t("settings.title")}
        title={t("settings.devices")}
        right={
          devices.isLoading ? undefined : (
            <span className="num text-[11px] text-muted">
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
          {PROVIDERS.map(({ key, name, connectable }) => {
            const d = byProvider.get(key);
            const connected = d?.status === "active";
            return (
              <div
                key={key}
                className="flex items-center justify-between gap-3 border-b border-hairline py-2.5 last:border-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-ink">{name}</span>
                    {d?.is_main && <Badge tone="primary">{t("settings.main_device")}</Badge>}
                    {connected ? (
                      <Badge tone="positive">{t("settings.connected")}</Badge>
                    ) : d ? (
                      <Badge tone="warning">{d.status}</Badge>
                    ) : null}
                  </div>
                  <div className="num mt-0.5 text-[11px] text-muted">
                    {connected
                      ? `${t("settings.connected")} · ${
                          d?.last_synced_at
                            ? new Date(d.last_synced_at).toLocaleString()
                            : t("settings.never")
                        }`
                      : connectable
                        ? t("settings.coming_soon")
                        : "tools/garmin_sync.py connect"}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {connected && !d?.is_main && (
                    <Button
                      variant="ghost"
                      className="!h-7 !px-2.5 text-[12px]"
                      disabled={setMain.isPending}
                      onClick={() => d && setMain.mutate(d.integration_id)}
                    >
                      {t("settings.set_main")}
                    </Button>
                  )}
                  {connectable && !connected && (
                    <Button
                      variant="ghost"
                      className="!h-7 !px-2.5 text-[12px]"
                      disabled={connect.isPending}
                      onClick={() => connect.mutate(key)}
                      icon={<ExternalLink size={12} />}
                    >
                      {t("settings.connect")}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {flowError && (
        <div className="mt-3">
          <ErrorNote message={flowError} />
        </div>
      )}
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
      api.put("/me/password", { current_password: current, new_password: next }),
    onSuccess: () => {
      setDone(true);
      setCurrent("");
      setNext("");
    },
  });

  return (
    <Card>
      <CardHeader eyebrow={t("settings.account")} title={t("settings.password")} />
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
      className="mono inline-flex items-center gap-1.5 rounded-sm border border-hairline bg-surface2 px-2 py-1 text-[11px] text-ink2 hover:bg-surface3"
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
      {copied ? <Check size={11} className="text-positiveText" /> : <Copy size={11} />}
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
        eyebrow={t("settings.owner")}
        title={t("settings.invites")}
        right={
          <Button
            variant="ghost"
            className="!h-7 !px-2.5 text-[12px]"
            disabled={mint.isPending}
            onClick={() => mint.mutate()}
            icon={<Plus size={12} />}
          >
            {t("settings.mint_invite")}
          </Button>
        }
      />
      <p className="mb-3 text-[12px] leading-relaxed text-muted">{t("settings.invites_hint")}</p>
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
                <span className="num text-[11px] text-muted">
                  {t("settings.expires")} {new Date(inv.expires_at).toLocaleDateString()}
                </span>
              </div>
              {!inv.used_by && !inv.expired && (
                <button
                  type="button"
                  aria-label={t("settings.revoke")}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-control text-muted hover:bg-alertSoft hover:text-alertText"
                  onClick={() => revoke.mutate(inv.id)}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {revoke.isError && (
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
          <div className="text-[13px] font-medium text-ink">{me.ai_access_tier}</div>
        </div>
        <div>
          <div className="eyebrow mb-1">{t("settings.timezone")}</div>
          <div className="num text-[13px] font-medium text-ink">{me.timezone}</div>
        </div>
        <div>
          <div className="eyebrow mb-1">{t("settings.height")}</div>
          <div className="num text-[13px] font-medium text-ink">
            {me.height_cm ? `${fmtNum(me.height_cm)} cm` : "—"}
          </div>
        </div>
        <div>
          <div className="eyebrow mb-1">{t("settings.dob")}</div>
          <div className="num text-[13px] font-medium text-ink">{me.dob ?? "—"}</div>
        </div>
      </div>
    </Card>
  );
}

/* --------------------------------------------------------------------- page */

export default function SettingsPage() {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);

  // The session effect populates the ui store AFTER first paint; until me
  // exists the profile section has nothing to initialize its fields from.
  if (!me) return <Loading />;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="eyebrow">
          {t("app.name")} {t("app.suffix")}
        </div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          {t("settings.title")}
        </h1>
      </div>
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
        <ProfileSection me={me} />
        <AppearanceSection />
        <DevicesSection />
        <div className="flex flex-col gap-4">
          <AccountSection />
          <SecuritySection />
          {me.role === "owner" && <InvitesSection />}
        </div>
      </div>
    </div>
  );
}
