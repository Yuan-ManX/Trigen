import { create } from "zustand";
import { persist } from "zustand/middleware";
import { translations, type Lang, type Translation } from "@/data/content";

interface LanguageState {
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggle: () => void;
}

export const useLanguage = create<LanguageState>()(
  persist(
    (set, get) => ({
      lang: "en",
      setLang: (lang) => set({ lang }),
      toggle: () => set({ lang: get().lang === "en" ? "zh" : "en" }),
    }),
    {
      name: "trigen-lang",
      partialize: (state) => ({ lang: state.lang }),
    }
  )
);

export function useTranslation(): Translation {
  const lang = useLanguage((s) => s.lang);
  return translations[lang];
}
