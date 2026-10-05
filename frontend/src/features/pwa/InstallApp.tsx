import { useEffect, useState } from "react";
import { Download, Share } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clearInstallPrompt, getInstallPrompt, type InstallPromptEvent } from "./installPrompt";

function isInstalled() {
  return window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function isAppleMobile() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

/** Render in navigation or settings to offer the browser's native install flow. */
export function InstallApp() {
  const { t } = useTranslation();
  const [prompt, setPrompt] = useState<InstallPromptEvent | null>(getInstallPrompt);
  const [installed, setInstalled] = useState(isInstalled);
  const [showAppleSteps, setShowAppleSteps] = useState(false);
  const appleMobile = isAppleMobile();

  useEffect(() => {
    const onPrompt = (event: InstallPromptEvent) => {
      event.preventDefault();
      setPrompt(event);
    };
    const onInstalled = () => {
      setInstalled(true);
      setPrompt(null);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (!window.isSecureContext || installed || (!prompt && !appleMobile)) return null;

  if (appleMobile) {
    return (
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => setShowAppleSteps((shown) => !shown)}
          aria-expanded={showAppleSteps}
          className="inline-flex items-center gap-2 rounded-lg border border-hairline px-3 py-2 text-sm text-ink hover:bg-surface2"
        >
          <Share size={16} aria-hidden="true" />
          {t("pwa.install")}
        </button>
        {showAppleSteps && (
          <p className="max-w-xs text-xs text-muted">
            {t("pwa.ios_steps", { share: t("pwa.share"), add: t("pwa.add_to_home") })}
          </p>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={async () => {
        if (!prompt) return;
        await prompt.prompt();
        const choice = await prompt.userChoice;
        clearInstallPrompt();
        setPrompt(null);
        if (choice.outcome === "accepted") setInstalled(true);
      }}
      className="inline-flex items-center gap-2 rounded-lg border border-hairline px-3 py-2 text-sm text-ink hover:bg-surface2"
    >
      <Download size={16} aria-hidden="true" />
      {t("pwa.install")}
    </button>
  );
}
