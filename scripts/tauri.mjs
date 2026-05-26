import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);

function run(command, commandArgs) {
  const result = spawnSync(command, commandArgs, {
    cwd: repoRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function tauriCommand() {
  const binary = process.platform === "win32" ? "tauri.cmd" : "tauri";
  const localBinary = path.join(repoRoot, "node_modules", ".bin", binary);
  return fs.existsSync(localBinary) ? localBinary : "tauri";
}

function validateBundledTursoConfig() {
  const configPath = path.join(repoRoot, "configuracoes.json");
  let config = {};
  if (fs.existsSync(configPath)) {
    config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  }

  const url = String(config.turso_database_url || "").trim();
  const token = String(config.turso_auth_token || "").trim();
  const hasEnv = Boolean(process.env.TURSO_DATABASE_URL && process.env.TURSO_AUTH_TOKEN);

  if (url && token) {
    return;
  }

  if (hasEnv) {
    console.error(
      [
        "Build interrompida: TURSO_DATABASE_URL/TURSO_AUTH_TOKEN existem no ambiente,",
        "mas nao estao em configuracoes.json. O instalador local empacota esse arquivo,",
        "entao outro computador ficaria sem login. Use o workflow de release ou prepare",
        "configuracoes.json antes de buildar localmente.",
      ].join(" "),
    );
    process.exit(1);
  }

  console.error(
    [
      "Build interrompida: configuracoes.json nao tem turso_database_url/turso_auth_token.",
      "Esse instalador funcionaria apenas em maquinas que ja tenham configuracao local.",
      "Use o workflow de release com os secrets TURSO_DATABASE_URL e TURSO_AUTH_TOKEN.",
    ].join(" "),
  );
  process.exit(1);
}

run("node", ["scripts/sync_version.mjs"]);

if (args[0] === "build" && process.env.AUTO_LIQUID_ALLOW_UNCONFIGURED_BUILD !== "1") {
  validateBundledTursoConfig();
}

run(tauriCommand(), args);
