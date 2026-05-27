"use client";

import { useEffect } from "react";

/**
 * Detecta a plataforma na inicialização e adiciona uma classe ao <html> para
 * ajustes de CSS específicos por plataforma.
 *
 * No Windows, `backdrop-filter: blur()` é muito lento durante o scroll no
 * WebView2 (Edge Chromium). A classe `platform-windows` é usada no CSS global
 * para desativar todos os backdrop-blur e ajustar opacidades dos vidros.
 */
export function PlatformSync() {
  useEffect(() => {
    const ua = navigator.userAgent ?? "";
    const isWindows =
      ua.includes("Windows") ||
      (navigator.platform ?? "").startsWith("Win");

    if (isWindows) {
      document.documentElement.classList.add("platform-windows");
    }
  }, []);

  return null;
}
