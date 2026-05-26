import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const versionPath = path.join(repoRoot, "VERSION");
const args = process.argv.slice(2);
const checkOnly = args.includes("--check");
const rawArg = args.find((arg) => !arg.startsWith("--"));

function normalizeVersion(value) {
  const raw = String(value || "").trim().replace(/^v/i, "");
  const match = raw.match(/^(\d+)(?:\.(\d+))?(?:\.(\d+))?([+-][0-9A-Za-z.-]+)?$/);
  if (!match) {
    throw new Error(`Versao invalida: "${value}". Use uma tag/versao SemVer, ex.: v3.0 ou v3.0.4.`);
  }
  const [, major, minor = "0", patch = "0", suffix = ""] = match;
  return `${major}.${minor}.${patch}${suffix}`;
}

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(repoRoot, relativePath), "utf8"));
}

function writeFileIfChanged(relativePath, nextContent) {
  const fullPath = path.join(repoRoot, relativePath);
  const previous = fs.existsSync(fullPath) ? fs.readFileSync(fullPath, "utf8") : "";
  if (previous === nextContent) {
    return false;
  }
  if (checkOnly) {
    throw new Error(`${relativePath} esta fora de sincronia com VERSION.`);
  }
  fs.writeFileSync(fullPath, nextContent, "utf8");
  return true;
}

function writeJson(relativePath, data) {
  return writeFileIfChanged(relativePath, `${JSON.stringify(data, null, 2)}\n`);
}

function replaceRequired(relativePath, pattern, replacement) {
  const fullPath = path.join(repoRoot, relativePath);
  const previous = fs.readFileSync(fullPath, "utf8");
  if (!pattern.test(previous)) {
    throw new Error(`Nao encontrei o campo de versao esperado em ${relativePath}.`);
  }
  pattern.lastIndex = 0;
  return writeFileIfChanged(relativePath, previous.replace(pattern, replacement));
}

function syncCargoLock(version) {
  const relativePath = "src-tauri/Cargo.lock";
  const fullPath = path.join(repoRoot, relativePath);
  if (!fs.existsSync(fullPath)) {
    return false;
  }

  const previous = fs.readFileSync(fullPath, "utf8");
  const blocks = previous.split(/(?=^\[\[package\]\]$)/m);
  let foundAppPackage = false;
  const next = blocks
    .map((block) => {
      if (!/^name\s*=\s*"app"$/m.test(block)) {
        return block;
      }
      foundAppPackage = true;
      if (!/^version\s*=\s*"[^"]+"$/m.test(block)) {
        throw new Error(`Nao encontrei o campo version do pacote app em ${relativePath}.`);
      }
      return block.replace(/^version\s*=\s*"[^"]+"$/m, `version = "${version}"`);
    })
    .join("");

  if (!foundAppPackage) {
    console.warn(`Aviso: pacote app nao encontrado em ${relativePath}; deixando o Cargo atualizar o lock.`);
    return false;
  }

  return writeFileIfChanged(relativePath, next);
}

const version = normalizeVersion(rawArg || fs.readFileSync(versionPath, "utf8"));
const changed = [];

if (writeFileIfChanged("VERSION", `${version}\n`)) changed.push("VERSION");

for (const relativePath of ["package.json", "frontend/package.json"]) {
  const data = readJson(relativePath);
  data.version = version;
  if (writeJson(relativePath, data)) changed.push(relativePath);
}

for (const relativePath of ["package-lock.json", "frontend/package-lock.json"]) {
  if (!fs.existsSync(path.join(repoRoot, relativePath))) continue;
  const data = readJson(relativePath);
  data.version = version;
  if (data.packages?.[""]) {
    data.packages[""].version = version;
  }
  if (writeJson(relativePath, data)) changed.push(relativePath);
}

{
  const data = readJson("src-tauri/tauri.conf.json");
  data.version = version;
  if (writeJson("src-tauri/tauri.conf.json", data)) changed.push("src-tauri/tauri.conf.json");
}

if (
  replaceRequired(
    "src-tauri/Cargo.toml",
    /(^\[package\][\s\S]*?^version\s*=\s*)"[^"]+"/m,
    `$1"${version}"`,
  )
) {
  changed.push("src-tauri/Cargo.toml");
}

if (syncCargoLock(version)) {
  changed.push("src-tauri/Cargo.lock");
}

console.log(
  changed.length
    ? `Versao ${version} sincronizada em: ${changed.join(", ")}`
    : `Versao ${version} ja estava sincronizada.`,
);
