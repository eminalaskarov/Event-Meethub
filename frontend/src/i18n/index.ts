import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import az from "./az.json";
import en from "./en.json";

export const LANGUAGES = ["en", "az"] as const;
export type Language = (typeof LANGUAGES)[number];

const STORAGE_KEY = "eventhub.language";
const DEFAULT_LANGUAGE: Language = "en";

function savedLanguage(): Language {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return LANGUAGES.includes(value as Language) ? (value as Language) : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

function updateDocument(language: string) {
  document.documentElement.lang = language;
  document.title = i18n.t("navbar.brand");
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    az: { translation: az },
  },
  lng: savedLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  interpolation: { escapeValue: false }, // React already escapes rendered text
});

updateDocument(i18n.language);

i18n.on("languageChanged", (language) => {
  updateDocument(language);
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Storage can be unavailable in private browsing; switching still works.
  }
});

export default i18n;