import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Button } from "../../components/kit";

type Category = "bug" | "idea" | "other";

export function FeedbackButton() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<"sent" | "error" | null>(null);
  const location = useLocation();
  const opener = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const [category, setCategory] = useState<Category>("bug");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!notice || open) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice, open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      if (e.key !== "Tab") return;
      const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button, input, textarea, select") ?? []);
      const first = nodes[0], last = nodes.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    dialog.current?.querySelector<HTMLElement>("select")?.focus();
    return () => { document.removeEventListener("keydown", onKey); opener.current?.focus(); };
  }, [open]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pending || !message.trim()) return;
    setPending(true); setNotice(null);
    try {
      await api.post("/api/feedback", { category, message: message.trim(), page_url: location.pathname });
      setOpen(false); setMessage(""); setNotice("sent");
    } catch { setNotice("error"); }
    finally { setPending(false); }
  }

  return <>
    <button ref={opener} type="button" onClick={() => { setNotice(null); setOpen(true); }} className="border border-hairline px-3 py-2 text-[12px] text-muted hover:bg-surface2 hover:text-ink">{t("feedback.button")}</button>
    {notice && !open && <div role="status" className={`fixed bottom-5 right-5 z-[70] max-w-sm border bg-surface px-4 py-3 text-sm shadow-lg ${notice === "error" ? "border-alert text-alertText" : "border-hairline text-ink"}`}>{t(notice === "sent" ? "feedback.sent" : "feedback.error")}</div>}
    {open && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
      <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="feedback-title" className="w-full max-w-lg border border-hairline bg-surface p-6 shadow-xl">
        <h2 id="feedback-title" className="text-lg font-medium">{t("feedback.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("feedback.page", { page: location.pathname })}</p>
        <p className="mt-3 text-xs leading-relaxed text-muted">{t("feedback.privacy_notice")}</p>
        <form onSubmit={submit} className="mt-5 space-y-4">
          <label className="block text-sm">{t("feedback.category")}<select value={category} onChange={(e) => setCategory(e.target.value as Category)} className="mt-1 block w-full border border-hairline bg-surface px-3 py-2"><option value="bug">{t("feedback.bug")}</option><option value="idea">{t("feedback.idea")}</option><option value="other">{t("feedback.other")}</option></select></label>
          <label className="block text-sm">{t("feedback.message")}<textarea required minLength={1} maxLength={2000} rows={5} value={message} onChange={(e) => setMessage(e.target.value)} className="mt-1 block w-full resize-y border border-hairline bg-surface px-3 py-2" /></label>
          {notice === "error" && <p role="alert" className="text-sm text-alertText">{t("feedback.error")}</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setOpen(false)}>{t("feedback.cancel")}</Button><Button type="submit" disabled={pending || !message.trim()}>{pending ? t("feedback.sending") : t("feedback.submit")}</Button></div>
        </form>
      </div>
    </div>}
  </>;
}
