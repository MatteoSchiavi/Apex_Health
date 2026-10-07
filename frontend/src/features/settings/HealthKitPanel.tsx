import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Badge, Button, Card, CardHeader, ErrorNote, Loading } from "../../components/kit";

interface HealthKitDevice {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  absolute_expires_at: string;
  checkpoint: number;
  last_success_at: string | null;
}
interface PairingCode {
  code: string;
  expires_at: string;
}

/** One-time pairing codes stay in component memory, never browser storage or query data. */
export default function HealthKitPanel() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [now, setNow] = useState(Date.now());
  const [codeExpired, setCodeExpired] = useState(false);
  const devices = useQuery({
    queryKey: ["healthkit", "devices"],
    queryFn: () => api.get<HealthKitDevice[]>("/healthkit/devices"),
  });
  const create = useMutation({
    mutationFn: async () => {
      setPairing(null);
      setCodeExpired(false);
      const result = await api.post<PairingCode>("/healthkit/pairings");
      if (!result.code || result.code.length > 128 || !Number.isFinite(Date.parse(result.expires_at))) {
        throw new Error("Invalid pairing response");
      }
      // Do not return this response: TanStack's mutation cache should not retain a code.
      setNow(Date.now());
      setPairing(result);
    },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.delete<void>(`/healthkit/devices/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["healthkit", "devices"] }),
  });

  useEffect(() => {
    if (!pairing) return;
    const refresh = () => {
      const current = Date.now();
      setNow(current);
      if (current >= Date.parse(pairing.expires_at)) {
        setPairing(null);
        setCodeExpired(true);
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => window.clearInterval(timer);
  }, [pairing]);

  const secondsRemaining = pairing ? Math.max(0, Math.ceil((Date.parse(pairing.expires_at) - now) / 1000)) : 0;
  const timeLabel = (value: string | null) => {
    if (!value) return t("healthKit.neverSynced");
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString(i18n.language) : t("healthKit.neverSynced");
  };

  return (
    <section aria-label={t("healthKit.title")} data-testid="healthkit-panel">
      <Card>
        <CardHeader title={t("healthKit.title")} right={<Badge tone="warning">{t("healthKit.developmentOnly")}</Badge>} />
        <div className="space-y-3 text-[13px] text-muted">
          <p>{t("healthKit.caveat")}</p>
          <p>{t("healthKit.pairHelp")}</p>
          <p>{t("healthKit.tokenHelp")}</p>
          <Button onClick={() => create.mutate()} disabled={create.isPending}>
            {t(create.isPending ? "healthKit.creatingCode" : "healthKit.createCode")}
          </Button>
          {pairing && secondsRemaining > 0 && (
            <div className="rounded-control border border-hairline bg-surface3 p-4" role="status">
              <div className="text-ink2">{t("healthKit.codeLabel")}</div>
              <output data-testid="healthkit-pairing-code" className="mt-2 block select-all break-all font-mono text-xl tracking-wider text-ink">
                {pairing.code}
              </output>
              <p className="mt-2">{t("healthKit.expiresIn", { seconds: secondsRemaining })}</p>
              <Button variant="ghost" onClick={() => setPairing(null)} className="mt-2">{t("healthKit.dismissCode")}</Button>
            </div>
          )}
          {codeExpired && <p role="status">{t("healthKit.codeExpired")}</p>}
          {create.isError && <ErrorNote message={t("healthKit.genericError")} />}
        </div>
        <h3 className="mt-6 text-[14px] font-medium text-ink">{t("healthKit.devices")}</h3>
        <p className="mt-2 text-[13px] text-muted">{t("healthKit.revokeHelp")}</p>
        {devices.isLoading && <Loading />}
        {devices.isError && <ErrorNote message={t("healthKit.loadError")} />}
        {devices.isSuccess && devices.data.length === 0 && <p className="mt-3 text-[13px] text-muted">{t("healthKit.emptyDevices")}</p>}
        <div className="mt-3 space-y-3">
          {devices.data?.map((device) => {
            const expired = Date.parse(device.absolute_expires_at) <= now;
            const inactive = Boolean(device.revoked_at) || expired;
            return (
              <article key={device.id} aria-label={device.name} className="rounded-control border border-hairline p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="font-medium text-ink">{device.name}</span>
                  <Badge tone={inactive ? "neutral" : "positive"}>{t(device.revoked_at ? "healthKit.revoked" : expired ? "healthKit.expiredDevice" : "healthKit.activeDevice")}</Badge>
                </div>
                <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-[12px] text-muted">
                  <div><dt>{t("healthKit.lastSync")}</dt><dd>{timeLabel(device.last_success_at)}</dd></div>
                  <div><dt>{t("healthKit.checkpoint")}</dt><dd>{device.checkpoint}</dd></div>
                </dl>
                {!inactive && (
                  <Button variant="danger" className="mt-3" disabled={revoke.isPending} onClick={() => revoke.mutate(device.id)}>
                    {t(revoke.isPending && revoke.variables === device.id ? "healthKit.revoking" : "healthKit.revoke")}
                  </Button>
                )}
              </article>
            );
          })}
        </div>
        {revoke.isError && <ErrorNote message={t("healthKit.genericError")} />}
      </Card>
    </section>
  );
}
