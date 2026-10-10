# Hospital Business Process Knowledge Base — Mayapada

Fumadocs site (Next.js 16, Fumadocs 16, Mermaid 12) that explains Indonesian hospital operations and maps them to the Mayapada Odoo codebase (`../odoo-revamp/mayapada`). Content is in Bahasa Indonesia.

## Run

```bash
pnpm install
pnpm dev                 # http://localhost:3000/docs
pnpm build && pnpm start # production
pnpm docs:check          # internal links, meta.json pages, Mermaid syntax
pnpm lint
```

Node 20+ (tested on Node 26, pnpm 11).

## Deploy (pm2)

`next.config.mjs` uses `output: 'standalone'`, so the host needs only Node + pm2 — no package install (the target server's registry link is too slow for `next`/`mermaid` tarballs). Build locally, then ship the bundle:

```bash
pnpm build
R=mqdd@100.115.174.40; D='~/apps/hospital-business-docs/app'
rsync -az --delete .next/standalone/ $R:$D/
rsync -az .next/static $R:$D/.next/
rsync -az public $R:$D/
ssh $R 'pm2 restart hospital-business-docs'   # first time:
# ssh $R 'cd ~/apps/hospital-business-docs/app && PORT=3200 HOSTNAME=0.0.0.0 pm2 start server.js --name hospital-business-docs && pm2 save'
```

Live at http://100.115.174.40:3200/docs (Tailscale).

## Layout

```text
content/docs/            MDX pages + meta.json (sidebar order)
src/components/mdx/      mermaid.tsx (client render, theme-aware), confidence.tsx (evidence badges), illustrations.tsx (SVG)
src/components/mdx.tsx   MDX component registry
scripts/docs-check.mjs   validation script
source.config.ts         remarkMdxMermaid: ```mermaid blocks → <Mermaid/>
```

## Writing rules

- Every important claim carries a `<Confidence level="general|verified|inferred|confirm|notfound" />` badge.
- Code references: `mayapada/<file>:<line>` against `odoo-revamp` commit `7e4772d`. Re-check line numbers after new commits.
- Synthetic data only. Never copy credentials, server IPs, or patient data from the repo, Airflow config, or project memory.
- Mermaid: use `<br/>` for line breaks (not `\n`), avoid `|` inside table cells; run `pnpm docs:check`.
