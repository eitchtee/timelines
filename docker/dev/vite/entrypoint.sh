#!/bin/sh
set -eu

# node_modules lives in an anonymous volume that survives rebuilds, so reinstall
# only when the manifests actually changed.
deps_hash="$(sha256sum package.json package-lock.json 2>/dev/null | sha256sum | cut -d ' ' -f 1)"
deps_stamp="node_modules/.deps-hash"

if [ ! -f "$deps_stamp" ] || [ "$(cat "$deps_stamp")" != "$deps_hash" ]; then
    echo "Installing frontend dependencies..."
    npm ci --no-audit --no-fund --prefer-offline || npm install --no-audit --no-fund
    printf '%s\n' "$deps_hash" > "$deps_stamp"
fi

exec npm run dev
