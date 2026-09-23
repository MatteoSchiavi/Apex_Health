import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";
import it from "../locales/it.json";

// Locale is baked into the account (users.locale) and mirrored in
// localStorage; the store reconciles after /me loads. No hardcoded strings
// in components — the check-i18n script greps for violations.
void i18next.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    it: { translation: it },
  },
  lng: document.documentElement.lang === "it" ? "it" : "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18next;
