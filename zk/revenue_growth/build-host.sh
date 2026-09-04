#!/bin/sh
set -eu

if [ "${RISC0_DEV_MODE+x}" = x ]; then
  echo "RISC0_DEV_MODE is forbidden for a production proof build" >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
exec cargo build --locked --release --manifest-path Cargo.toml -p revenue-growth-proof-host
