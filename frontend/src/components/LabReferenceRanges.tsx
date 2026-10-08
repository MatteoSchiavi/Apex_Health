import { useTranslation } from "react-i18next";

export const LAB_MARKERS = ["hemoglobin", "hematocrit", "ferritin", "iron", "wbc", "plt"] as const;

export function readLabReferenceRanges(form: FormData) {
  const ranges: Record<string, [number | null, number | null]> = {};
  for (const marker of LAB_MARKERS) {
    const parse = (bound: string) => {
      const raw = String(form.get(`reference_${marker}_${bound}`) ?? "").trim();
      return raw === "" ? null : Number(raw);
    };
    const low = parse("low"), high = parse("high");
    if (low !== null || high !== null) ranges[marker] = [low, high];
  }
  return ranges;
}

export function LabReferenceRanges({ markers = LAB_MARKERS }: { markers?: readonly string[] }) {
  const { t } = useTranslation();
  return <details className="col-span-full border-t border-hairline pt-4">
    <summary className="cursor-pointer text-[13px]">{t("physiology.lab_ranges")}</summary>
    <p className="my-3 text-[12px] text-muted">{t("physiology.lab_ranges_note")}</p>
    <div className="grid gap-3 sm:grid-cols-2">
      {markers.map(marker => <fieldset key={marker} className="min-w-0">
        <legend className="mb-2 text-[12px]">{t("design.lab_" + marker)}</legend>
        <div className="grid grid-cols-2 gap-2">
          {(["low", "high"] as const).map(bound => <label key={bound} className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">
            {t("physiology." + bound)}
            <input name={`reference_${marker}_${bound}`} aria-label={`${t("design.lab_" + marker)} · ${t("physiology." + bound)}`}
              type="number" step="any" className="min-w-0 w-full rounded-control border border-hairline bg-transparent px-3 py-2 text-ink" />
          </label>)}
        </div>
      </fieldset>)}
    </div>
  </details>;
}

export function LabReferenceInterval({ low, high, unit }: { low: number | null; high: number | null; unit: string | null }) {
  const { t } = useTranslation();
  if (low == null && high == null) return null;
  return <p className="mt-2 text-[12px] text-muted">{t("physiology.recorded_range")}: {low ?? "—"}–{high ?? "—"} {unit}</p>;
}
