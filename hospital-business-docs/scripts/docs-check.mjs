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

console.log(`${slugs.size} pages, ${diagrams} mermaid diagrams checked`);
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("OK: links, meta entries and mermaid syntax valid");
