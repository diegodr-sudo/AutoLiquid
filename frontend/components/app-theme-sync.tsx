"use client";

import { useEffect } from "react";
import { useTheme } from "next-themes";
import { fetchAppSettings, type AppSettings } from "@/lib/data";

const VALID_THEMES: AppSettings["temaWeb"][] = ["light", "dark", "system"];

export function AppThemeSync() {
  const { setTheme } = useTheme();

  useEffect(() => {
    let active = true;

    fetchAppSettings()
      .then((settings) => {
        if (!active) return;
        const theme = VALID_THEMES.includes(settings.temaWeb) ? settings.temaWeb : "light";
        setTheme(theme);
      })
      .catch(() => {
        // Mantém o tema inicial se o backend ainda não estiver disponível.
      });

    return () => {
      active = false;
    };
  }, [setTheme]);

  return null;
}
