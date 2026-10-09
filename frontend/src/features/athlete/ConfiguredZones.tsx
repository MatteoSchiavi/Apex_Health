import { useTranslation } from "react-i18next";
import { Button, Input } from "../../components/kit";
import type { ZoneConfiguration } from "./types";

export function ConfiguredZones({ kind, value, onChange }: { kind: "hr" | "power"; value?: ZoneConfiguration; onChange: (value?: ZoneConfiguration) => void }) {
  const { t } = useTranslation();
  return <fieldset className="space-y-3 border-t border-hairline pt-4"><legend className="text-[14px] font-medium">{t("athlete."+kind+"_zones")}</legend><p className="text-[12px] text-muted">{t("athlete.zones_note")}</p>
    {value && <><Input label={t("athlete.zones_effective")} type="date" value={value.effective_from} onChange={effective_from => onChange({ ...value, effective_from })} />{value.bands.map((band, i) => <div className="grid gap-3 sm:grid-cols-4" key={i}><Input label={t("athlete.zone_name")} value={band.name} onChange={name => onChange({ ...value, bands: value.bands.map((b,n) => n===i ? {...b,name} : b) })} /><Input label={t("athlete.zone_lower")} type="number" min={0} value={String(band.lower)} onChange={lower => onChange({ ...value, bands: value.bands.map((b,n) => n===i ? {...b,lower:Number(lower)} : b) })} /><Input label={t("athlete.zone_upper")} type="number" min={1} value={String(band.upper)} onChange={upper => onChange({ ...value, bands: value.bands.map((b,n) => n===i ? {...b,upper:Number(upper)} : b) })} /><Button variant="ghost" onClick={() => onChange(value.bands.length===1 ? undefined : { ...value, bands: value.bands.filter((_,n) => n!==i) })}>{t("athlete.remove_zone")}</Button></div>)}</>}
    <Button variant="ghost" disabled={(value?.bands.length ?? 0)>=10} onClick={() => onChange({ effective_from: value?.effective_from ?? "", bands: [...(value?.bands ?? []), { name: "", lower: value?.bands.at(-1)?.upper ?? 0, upper: (value?.bands.at(-1)?.upper ?? 0)+1 }] })}>{t("athlete.add_zone")}</Button>
  </fieldset>;
}
