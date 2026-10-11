// Citation to the Odoo codebase. `file` is relative to odoo-revamp/.
// Line/symbol accuracy is enforced by `pnpm docs:check`.
const REPO = "https://github.com/Mqdd27/bp-mypd/blob/master/odoo-revamp/";

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
  return (
    <a className="src-ref" href={REPO + file + anchor} target="_blank" rel="noreferrer">
      {symbol ? <code>{symbol}</code> : null}
      <span className="src-loc">
        {file}
        {loc}
      </span>
    </a>
  );
}
