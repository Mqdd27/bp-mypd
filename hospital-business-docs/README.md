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

The server holds a git clone at `~/apps/bp-mypd`; pm2 serves `hospital-business-docs/.next/standalone/server.js` straight from it (port 3200). `scripts/deploy.sh` (run on the server) does `git pull` → install → build → copies `static`/`public` into the standalone dir → `pm2 restart` (or first-time `pm2 start`) → prints `docs=200`. The site is briefly down while it builds.

```bash
git push            # deploy pulls from origin/master
pnpm ship           # = ssh to the server and run scripts/deploy.sh
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
