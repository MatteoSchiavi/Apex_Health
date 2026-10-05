import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./app/i18n";
import "./styles/tokens.css";
import App from "./app/App";
import "./features/pwa/installPrompt";

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js", { scope: "/" }).then((registration) => {
      // Check for updates when a user returns to the app. Existing pages are
      // never force-reloaded; the updated worker takes over when safe.
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") void registration.update();
      });
    }).catch(() => {
      // The site remains usable when offline support is unavailable.
    });
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
