// Citation to the Odoo codebase. `file` is relative to odoo-revamp/.
// Line/symbol accuracy is enforced by `pnpm docs:check`; the snippet is read
// from ../odoo-revamp at build time (pages are statically generated).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ServerCodeBlock } from "fumadocs-ui/components/codeblock.rsc";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "fumadocs-ui/components/ui/popover";

const REPO = "https://github.com/Mqdd27/bp-mypd/blob/master/odoo-revamp/";
const MAX_LINES = 15;
const cache = new Map<string, string[] | null>();

function readLines(file: string) {
  if (!cache.has(file)) {
    try {
      const path = join(process.cwd(), "../odoo-revamp", file);
      cache.set(file, readFileSync(path, "utf8").split("\n"));
    } catch {
      cache.set(file, null); // missing codebase: fall back to a plain link
    }
  }
  return cache.get(file);
}

const indentOf = (l: string) => l.match(/^ */)![0].length;

// Without `end`, stop where the cited block ends: the first non-blank line
// dedented back to the block's own level (next def/field/decorator).
function blockEnd(lines: string[], line: number) {
  const base = indentOf(lines[line - 1]);
  for (let i = line + 1; i <= lines.length; i++) {
    const l = lines[i - 1];
    if (l.trim() && indentOf(l) <= base && !/^\s*[)\]}]/.test(l)) return i - 1;
  }
  return lines.length;
}

function snippet(lines: string[], line: number, end?: number) {
  let last = Math.min(end ?? blockEnd(lines, line), lines.length);
  while (last > line && !lines[last - 1].trim()) last--;
  const stop = Math.min(last, line + MAX_LINES - 1);
  const chunk = lines.slice(line - 1, stop);
  const indent = Math.min(...chunk.filter((l) => l.trim()).map(indentOf));
  return {
    code: chunk.map((l) => l.slice(indent)).join("\n"),
    stop,
    cut: stop < last,
  };
}

export function Src({
  file,
  line,
  end,
  symbol,
}: {
  file: string;
  line?: number;
  end?: number;
  symbol?: string;
}) {
  const anchor = line ? `#L${line}${end ? `-L${end}` : ""}` : "";
  const loc = line ? `:${line}${end ? `–${end}` : ""}` : "";
  const href = REPO + file + anchor;
  const label = (
    <>
      {symbol ? <code>{symbol}</code> : null}
      <span className="src-loc">
        {file}
        {loc}
      </span>
    </>
  );

  const lines = line ? readLines(file) : null;
  if (!line || !lines) {
    return (
      <a className="src-ref" href={href} target="_blank" rel="noreferrer">
        {label}
      </a>
    );
  }

  const { code, stop, cut } = snippet(lines, line, end);
  return (
    <Popover>
      <PopoverTrigger className="src-ref">{label}</PopoverTrigger>
      <PopoverContent className="src-pop" align="start">
        <ServerCodeBlock
          code={code}
          lang="python"
          codeblock={{
            title: `${file}:${line}${stop > line ? `–${stop}` : ""}`,
            "data-line-numbers": true,
            "data-line-numbers-start": line,
            className: "my-0",
          }}
        />
        <a className="src-gh" href={href} target="_blank" rel="noreferrer">
          {cut ? "Lihat selengkapnya" : "Buka"} di GitHub ↗
        </a>
      </PopoverContent>
    </Popover>
  );
}
