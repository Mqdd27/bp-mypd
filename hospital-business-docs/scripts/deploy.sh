#!/usr/bin/env bash
# Runs ON the server: pull, build, swap the standalone bundle into the pm2 app dir.
set -euo pipefail
cd ~/apps/bp-mypd/hospital-business-docs
APP=~/apps/hospital-business-docs/app
PNPM="npx -y pnpm@11.24.0"
git pull --ff-only
$PNPM install --frozen-lockfile --fetch-timeout=600000
$PNPM build
rsync -a --delete .next/standalone/ "$APP/"
rsync -a .next/static "$APP/.next/"
[ -d public ] && rsync -a public "$APP/"
pm2 restart hospital-business-docs >/dev/null
curl -s --retry 15 --retry-connrefused --retry-delay 1 -o /dev/null -w 'docs=%{http_code}\n' http://127.0.0.1:3200/docs
