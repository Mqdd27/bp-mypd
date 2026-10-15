#!/usr/bin/env bash
# Runs ON the server: pull, build, and serve .next/standalone from this repo with pm2.
# Braces make bash parse the whole file first, so `git pull` rewriting it mid-run is safe.
{
set -euo pipefail
cd ~/apps/bp-mypd/hospital-business-docs
PNPM="npx -y pnpm@11.24.0"
git pull --ff-only
$PNPM install --frozen-lockfile --fetch-timeout=600000
$PNPM build
cp -r .next/static .next/standalone/.next/
[ -d public ] && cp -r public .next/standalone/
pm2 restart hospital-business-docs >/dev/null 2>&1 ||
  (cd .next/standalone && PORT=3200 HOSTNAME=0.0.0.0 pm2 start server.js --name hospital-business-docs >/dev/null)
pm2 save >/dev/null
curl -s --retry 15 --retry-connrefused --retry-delay 1 -o /dev/null -w 'docs=%{http_code}\n' http://127.0.0.1:3200/docs
exit
}
