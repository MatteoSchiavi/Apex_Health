import { Component, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, ErrorNote } from "./kit";
function Fallback() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-lg py-12">
      <ErrorNote message={t("design.page_unavailable")} />
      <Button
        variant="ghost"
        className="mt-5"
        onClick={() => window.location.reload()}
      >
        {t("common.retry")}
      </Button>
    </div>
  );
}
export class PageBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <Fallback /> : this.props.children;
  }
}
