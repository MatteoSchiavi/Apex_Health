import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Button, ErrorNote, Loading, Empty } from "../../components/kit";
import { localDay } from "../../components/data";
export function useToday() {
  return localDay(useUi((s) => s.me?.timezone));
}
export function useLab<T>(path: string) {
  const uid = useUi((s) => s.me?.user_id);
  return useQuery({
    queryKey: ["lab", uid, path],
    queryFn: () => api.get<T>(path),
    staleTime: 30000,
    refetchInterval: path === "/lab/jobs" ? 5000 : false,
  });
}
export function useAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      path,
      body,
      method = "post",
    }: {
      path: string;
      body?: unknown;
      method?: "post" | "delete" | "put" | "patch";
    }) => (method === "delete" ? api.delete(path) : api[method](path, body)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lab"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["context-docs"] });
    },
  });
}
export const inputClass =
  "w-full border border-hairline bg-transparent px-3 py-2.5 text-[13px] outline-none focus:border-ink";
export function Field({
  name,
  label,
  type = "text",
  value,
  required = false,
  min,
  max,
  children,
}: {
  name: string;
  label: string;
  type?: string;
  value?: string | number;
  required?: boolean;
  min?: number | string;
  max?: number | string;
  children?: ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted">
      <span>{label}</span>
      {children ? (
        <select name={name} defaultValue={value} className={inputClass}>
          {children}
        </select>
      ) : type === "textarea" ? (
        <textarea
          className={inputClass}
          name={name}
          defaultValue={value}
          maxLength={16000}
          rows={3}
          required={required}
        />
      ) : (
        <input
          className={inputClass}
          name={name}
          type={type}
          step={type === "number" ? "any" : undefined}
          defaultValue={value}
          required={required}
          min={min}
          max={max}
        />
      )}
    </label>
  );
}
export function Form({
  children,
  onSave,
  pending,
  error,
  label,
}: {
  children: ReactNode;
  onSave: (data: FormData) => void;
  pending?: boolean;
  error?: Error | null;
  label?: string;
}) {
  const { t } = useTranslation();
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(new FormData(e.currentTarget));
      }}
    >
      {children}
      <div>
        <Button type="submit" disabled={pending}>
          {label ?? t("lab.save")}
        </Button>
      </div>
      {error && <ErrorNote message={error.message} />}
    </form>
  );
}
export const str = (f: FormData, key: string) => String(f.get(key) ?? "");
export const num = (f: FormData, key: string) =>
  str(f, key) === "" ? null : Number(f.get(key));
export function human(value: string) {
  return value.replaceAll("_", " ");
}
export function Value({ value }: { value: unknown }) {
  if (value == null) return <span className="text-muted">—</span>;
  if (typeof value === "boolean") return <span>{value ? "✓" : "—"}</span>;
  if (Array.isArray(value))
    return (
      <div className="flex flex-col gap-2">
        {value.map((v, i) => (
          <Value key={i} value={v} />
        ))}
      </div>
    );
  if (typeof value === "object")
    return (
      <dl className="flex flex-col gap-2">
        {Object.entries(value as Record<string, unknown>)
          .filter(([k]) => !k.startsWith("_"))
          .map(([k, v]) => (
            <div
              key={k}
              className="grid grid-cols-[minmax(80px,1fr)_2fr] gap-3"
            >
              <dt className="text-muted">{human(k)}</dt>
              <dd className="min-w-0 break-words">
                <Value value={v} />
              </dd>
            </div>
          ))}
      </dl>
    );
  return (
    <span className="whitespace-pre-wrap break-words">{String(value)}</span>
  );
}
export function QueryState({
  loading,
  error,
  empty,
}: {
  loading: boolean;
  error: boolean;
  empty?: boolean;
}) {
  const { t } = useTranslation();
  return loading ? (
    <Loading />
  ) : error ? (
    <ErrorNote />
  ) : empty ? (
    <Empty>{t("lab.empty")}</Empty>
  ) : null;
}
