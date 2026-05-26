"use client";

import type { AuthSession } from "@/lib/data";

const STORE_PATH = ".settings.dat";
const STORAGE_KEY = "autoliquid_auth_session";

async function getTauriStore() {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
    return null;
  }
  try {
    const { Store } = await import("@tauri-apps/plugin-store");
    return Store.load(STORE_PATH, {
      defaults: {},
      autoSave: true,
      overrideDefaults: true,
    });
  } catch {
    return null;
  }
}

export async function readStoredAuthSession(): Promise<AuthSession | null> {
  const store = await getTauriStore();
  const session = store
    ? await store.get<AuthSession>("auth")
    : typeof window !== "undefined"
      ? JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null") as AuthSession | null
      : null;
  if (!session?.token || !session.username || !session.role) return null;
  return session;
}

export async function writeStoredAuthSession(session: AuthSession): Promise<void> {
  const store = await getTauriStore();
  if (store) {
    await store.set("auth", session);
    await store.save();
    return;
  }
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  }
}

export async function clearStoredAuthSession(): Promise<void> {
  const store = await getTauriStore();
  if (store) {
    await store.delete("auth");
    await store.save();
    return;
  }
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}
