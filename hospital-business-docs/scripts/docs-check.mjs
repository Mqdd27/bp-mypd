// Validates internal /docs links and meta.json page lists against content/docs.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative } from "node:path";

const root = "content/docs";
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else files.push(p);
  }
})(root);

const slugs = new Set(
  files
    .filter((f) => f.endsWith(".mdx"))
    .map((f) => "/docs/" + relative(root, f).replace(/\.mdx$/, "").replace(/(^|\/)index$/, ""))
    .map((s) => s.replace(/\/$/, "")),
);

const errors = [];
for (const f of files.filter((f) => f.endsWith(".mdx"))) {
  const text = readFileSync(f, "utf8");
  for (const m of text.matchAll(/\]\((\/docs[^)#\s]*)|href="(\/docs[^"#]*)"/g)) {
    const link = (m[1] ?? m[2]).replace(/\/$/, "");
    if (!slugs.has(link)) errors.push(`${f}: broken link ${link}`);
  }
}
for (const f of files.filter((f) => f.endsWith("meta.json"))) {
  const dir = f.replace(/\/meta\.json$/, "");
  for (const page of JSON.parse(readFileSync(f, "utf8")).pages ?? []) {
    if (page.startsWith("---")) continue;
    if (!existsSync(join(dir, page + ".mdx")) && !existsSync(join(dir, page))) errors.push(`${f}: missing page ${page}`);
  }
}

// <Src file line end symbol>: file must exist, line in range, symbol's last
// segment must appear on line..end (or line+2 for decorators/one-liners).
const codeRoot = "../odoo-revamp";
const srcFiles = new Map();
let cites = 0;
for (const f of files.filter((f) => f.endsWith(".mdx"))) {
  for (const m of readFileSync(f, "utf8").matchAll(/<Src\s([^>]*?)\/>/g)) {
    cites++;
    const a = Object.fromEntries([...m[1].matchAll(/(\w+)=(?:"([^"]*)"|\{(\d+)\})/g)].map((x) => [x[1], x[2] ?? Number(x[3])]));
    const path = join(codeRoot, a.file ?? "");
    if (!a.file || !existsSync(path)) { errors.push(`${f}: <Src> file not found ${a.file}`); continue; }
    if (!srcFiles.has(path)) srcFiles.set(path, readFileSync(path, "utf8").split("\n"));
    const lines = srcFiles.get(path);
    const name = a.symbol?.split(".").pop().replace(/\(\)$/, "");
    if (a.line && (a.line > lines.length || (a.end && a.end < a.line))) { errors.push(`${f}: <Src> ${a.file}:${a.line} out of range`); continue; }
    if (!name) continue;
    const re = new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`);
    if (!a.line) {
      if (!lines.some((l) => re.test(l))) errors.push(`${f}: <Src> symbol ${a.symbol} not in ${a.file}`);
    } else if (!lines.slice(a.line - 1, Math.max(a.end ?? 0, a.line + 2)).some((l) => re.test(l))) {
      const hit = lines.findIndex((l) => new RegExp(`(class|def)\\s+${name}\\b|^\\s*_name\\s*=\\s*['"]${name}['"]`).test(l));
      errors.push(`${f}: <Src> ${a.symbol} not at ${a.file}:${a.line}${hit >= 0 ? ` (found at ${hit + 1})` : ""}`);
    }
  }
}

// Parse every ```mermaid block with the same library the site renders with.
// DOMPurify has no DOM in Node; grammar parsing doesn't need sanitizing, so no-op it.
const { default: DOMPurify } = await import("../node_modules/.pnpm/node_modules/dompurify/dist/purify.es.mjs"); // mermaid's own (pnpm-hoisted) copy
Object.assign(DOMPurify, { addHook() {}, removeHook() {}, removeHooks() {}, removeAllHooks() {}, sanitize: (x) => x });
const { default: mermaid } = await import("mermaid");
let diagrams = 0;
for (const f of files.filter((f) => f.endsWith(".mdx"))) {
  const text = readFileSync(f, "utf8");
  for (const m of text.matchAll(/```mermaid\n([\s\S]*?)```/g)) {
    diagrams++;
    try {
      await mermaid.parse(m[1]);
    } catch (e) {
      errors.push(`${f}: mermaid #${diagrams} ${String(e.message).split("\n").slice(0, 3).join(" ")}`);
    }
  }
}

console.log(`${slugs.size} pages, ${diagrams} mermaid diagrams, ${cites} code citations checked`);
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("OK: links, meta entries, mermaid syntax and code citations valid");
