#!/bin/sh
set -eu

if [ "${RISC0_DEV_MODE+x}" = x ]; then
  echo "RISC0_DEV_MODE is forbidden for a production proof build" >&2
  exit 1
fi

if [ "${RISC0_SKIP_BUILD+x}" = x ]; then
  echo "RISC0_SKIP_BUILD is forbidden for a production proof build" >&2
  exit 1
fi

if [ "${RUSTFLAGS+x}" = x ] || [ "${CARGO_ENCODED_RUSTFLAGS+x}" = x ] || \
   [ "${RUSTC_WRAPPER+x}" = x ] || [ "${RUSTC_WORKSPACE_WRAPPER+x}" = x ]; then
  echo "external Rust compiler overrides are forbidden for a reproducible proof build" >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
UNSAFE_CONTEXT_LINK=$(
  find "$SCRIPT_DIR" \
    -path "$SCRIPT_DIR/target" -prune -o \
    -type l -print -quit
)
if [ -n "$UNSAFE_CONTEXT_LINK" ]; then
  echo "proof build context must not contain symbolic links" >&2
  exit 1
fi
UNSAFE_CONTEXT_FILE=$(
  find "$SCRIPT_DIR" \
    -path "$SCRIPT_DIR/target" -prune -o \
    -type f \( \
      -name '.env' -o -name '.env.*' -o -name '*.pem' -o \
      -name '*.key' -o -name '*.p12' -o -name '*.pfx' -o \
      -name '.netrc' -o -name '.npmrc' -o -name '.pypirc' -o \
      -name 'credentials*' -o -name 'id_rsa*' -o -name 'id_ed25519*' \
    \) -print -quit
)
if [ -n "$UNSAFE_CONTEXT_FILE" ]; then
  echo "proof build context contains a forbidden credential-like file" >&2
  exit 1
fi
cd "$SCRIPT_DIR"
cargo build --locked --release --manifest-path Cargo.toml -p revenue-growth-proof-host

HOST_BINARY="$SCRIPT_DIR/target/release/revenue-growth-proof-host"
if [ "$(uname -s)" = "Darwin" ]; then
  command -v python3.11 >/dev/null 2>&1 || {
    echo "Python 3.11 is required to normalize the macOS proof host" >&2
    exit 1
  }
  codesign --remove-signature "$HOST_BINARY"
  python3.11 "$SCRIPT_DIR/normalize_macos_host.py" "$HOST_BINARY"
  codesign --force --sign - --timestamp=none \
    --identifier org.vfas.revenue-growth-proof-host "$HOST_BINARY"
fi
