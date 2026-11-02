import { useTranslation } from "react-i18next";
import { Button, ErrorNote } from "./kit";

/** A failed read must leave a visible way to recover, including cached results. */
export function ReadError({ retry, pending, stale = false, label }: {
  retry: () => void;
  pending: boolean;
  stale?: boolean;
  label?: string;
}) {
  const { t } = useTranslation();
  return <div className="space-y-3" data-testid="read-error">
    <ErrorNote message={t(stale ? "readRecovery.refresh_error" : "readRecovery.load_error")} />
    <Button variant="ghost" disabled={pending} onClick={retry}>
      {pending ? t("common.loading") : label ?? t("common.retry")}
    </Button>
  </div>;
}
