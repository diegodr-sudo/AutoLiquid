"use client";

import { useEffect } from "react";
import { useTheme } from "next-themes";
import { invoke } from "@tauri-apps/api/core";

export function ThemeIconSync() {
  const { resolvedTheme, theme } = useTheme();

  useEffect(() => {
    const selectedTheme = theme === "system" ? "system" : resolvedTheme ?? "light";
    invoke("set_app_theme_icon", { theme: selectedTheme }).catch(() => {
      // Ignora falha fora do ambiente Tauri (ex.: execução web).
    });
  }, [resolvedTheme, theme]);

  return null;
}
