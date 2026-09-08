#!/usr/bin/env bash
set -euo pipefail
# This script can be a local source entry or a published bootstrap; URLs are not live yet.
vfa_source=""
vfa_version=""
if [[ "${1:-}" == --version ]]; then vfa_version="${2:?release required}"; shift 2; fi
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  vfa_source="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
if [[ "$(uname -s)" != Darwin ]]; then
  printf '%s\n' 'This launcher supports macOS. Use the advanced guide for Linux.'; exit 1
fi
vfa_root="$HOME/Library/Application Support/Verifiable Financial Agent"
umask 077
mkdir -p "$vfa_root/bin" "$vfa_root/logs" "$vfa_root/packages"
vfa_source_mode=yes
if [[ ! -f "$vfa_source/installer/Dockerfile" || -n "$vfa_version" ]]; then
  vfa_source_mode=no
  vfa_download="$(mktemp -d "$vfa_root/packages/download.XXXXXX")"
  vfa_api='https://api.github.com/repos/linyiji/verifiable-financial-ai-agent/releases'
  vfa_ref=latest
  if [[ -n "$vfa_version" ]]; then
    [[ "$vfa_version" =~ ^[a-zA-Z0-9._-]+$ ]] || exit 1
    vfa_ref="tags/$vfa_version"
  fi
  curl -fsSL "$vfa_api/$vfa_ref" -o "$vfa_download/release.json" || { printf '%s\n' 'PUBLICATION_REQUIRED: No accepted installer release is available.'; exit 1; }
  vfa_version="$(plutil -extract tag_name raw -o - "$vfa_download/release.json")"
  [[ "$(plutil -extract draft raw -o - "$vfa_download/release.json")" == false ]] || exit 1
  if [[ "$vfa_ref" == latest ]]; then
    [[ "$(plutil -extract prerelease raw -o - "$vfa_download/release.json")" == false ]] || exit 1
  fi
  [[ "$vfa_version" =~ ^[a-zA-Z0-9._-]+$ ]] || exit 1
  vfa_prefix="https://github.com/linyiji/verifiable-financial-ai-agent/releases/download/$vfa_version/"
  curl -fsSL "${vfa_prefix}evaluator-manifest.json" -o "$vfa_download/manifest.json" || { printf '%s\n' 'PUBLICATION_REQUIRED: This release has no installer package.'; exit 1; }
  vfa_url="$(plutil -extract archive_url raw -o - "$vfa_download/manifest.json")"
  vfa_sha="$(plutil -extract sha256 raw -o - "$vfa_download/manifest.json")"
  [[ "$(plutil -extract schema raw -o - "$vfa_download/manifest.json")" == 1 ]] || exit 1
  [[ "$(plutil -extract version raw -o - "$vfa_download/manifest.json")" == "$vfa_version" ]] || exit 1
  [[ "$vfa_url" == "$vfa_prefix"* && "$vfa_sha" =~ ^[a-f0-9]{64}$ ]] || exit 1
  curl -fsSL "$vfa_url" -o "$vfa_download/product.zip"
  vfa_actual="$(shasum -a 256 "$vfa_download/product.zip")"
  [[ "${vfa_actual%% *}" == "$vfa_sha" ]] || { printf '%s\n' 'INTEGRITY_FAILED: Do not run this package.'; exit 1; }
  if unzip -Z1 "$vfa_download/product.zip" | grep -Eq '(^/|(^|/)\.\.(/|$)|\\|:)'; then exit 1; fi
  unzip -q "$vfa_download/product.zip" -d "$vfa_download/app"
  vfa_source="$vfa_download/app"
fi
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Docker Desktop is required. Open its official installation guide? [y/N]'
  read -r vfa_answer </dev/tty
  if [[ "$vfa_answer" == y || "$vfa_answer" == Y ]]; then
    open 'https://docs.docker.com/desktop/setup/install/mac-install/'
  fi
  printf '%s\n' 'DOCKER_NOT_INSTALLED: Install Docker Desktop, then run this command again.'; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  open -a Docker || true
  printf '%s\n' 'DOCKER_NOT_RUNNING: Wait for Docker Desktop to be ready, then run the same command again.'; exit 1
fi
docker compose version >/dev/null
printf '%s\n' 'Verifiable Financial Agent — Preparing product (first build can take several minutes).'
if ! docker build -f "$vfa_source/installer/Dockerfile" -t vfa-evaluator:source "$vfa_source" >"$vfa_root/logs/build.log" 2>&1; then
  printf '%s\n' 'INSTALLATION_FAILED: Product preparation failed. Run the same command again; build details are in the private installation logs.'; exit 1
fi
cp "$vfa_source/installer/vfa.sh" "$vfa_root/bin/vfa"
chmod 700 "$vfa_root/bin/vfa"
# Per-user PATH only; no sudo or system-directory writes. Shell restart picks it up.
vfa_path_line='export PATH="$HOME/Library/Application Support/Verifiable Financial Agent/bin:$PATH"'
touch "$HOME/.zprofile"
grep -Fqx "$vfa_path_line" "$HOME/.zprofile" || printf '\n%s\n' "$vfa_path_line" >> "$HOME/.zprofile"
if [[ "$vfa_source_mode" == yes ]]; then
  "$vfa_root/bin/vfa" install --source "$@"
else
  "$vfa_root/bin/vfa" install --version "$vfa_version" "$@"
fi
