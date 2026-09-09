#!/usr/bin/env bash
set -euo pipefail
vfa_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
vfa_product_root="$vfa_root"
[[ ! -f "$vfa_root/product-root" ]] || vfa_product_root="$(<"$vfa_root/product-root")"
[[ "$vfa_product_root" == /* && -d "$vfa_product_root" ]] || { printf '%s\n' 'DIRECT_CREDENTIAL_NOT_FOUND: Selected product directory is unavailable.'; exit 1; }
[[ -f "$vfa_root/image" && -f "$vfa_root/revision" && -f "$vfa_root/image-digest" ]] || { printf '%s\n' 'RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED: Reinstall the selected release before starting.'; exit 1; }
vfa_image="$(<"$vfa_root/image")"
vfa_revision="$(<"$vfa_root/revision")"
vfa_digest="$(<"$vfa_root/image-digest")"
[[ "$vfa_image" == "$vfa_digest" && "$vfa_revision" =~ ^[a-f0-9]{40}$ && "$vfa_digest" =~ ^sha256:[a-f0-9]{64}$ ]] || { printf '%s\n' 'RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED: Reinstall the selected release before starting.'; exit 1; }
docker info >/dev/null 2>&1 || { printf '%s\n' 'DOCKER_NOT_RUNNING: Start Docker Desktop, then run vfa start.'; exit 1; }
vfa_args=(run --rm -i)
# Piped public bootstrap must acquire its credential terminal, not consume script stdin.
if [[ ! -t 0 && -r /dev/tty ]]; then exec </dev/tty; fi
[[ ! -t 0 ]] || vfa_args+=(-t)
vfa_args+=(-v /var/run/docker.sock:/var/run/docker.sock -v "$vfa_root:/install" -e "VFA_HOST_ROOT=$vfa_root")
[[ ! -d "$vfa_product_root/credentials" ]] || vfa_args+=(-v "$vfa_product_root/credentials:/credentials/product:ro")
[[ ! -d "$HOME/Downloads" ]] || vfa_args+=(-v "$HOME/Downloads:/credentials/downloads:ro")
[[ ! -d "$HOME/Desktop" ]] || vfa_args+=(-v "$HOME/Desktop:/credentials/desktop:ro")
docker "${vfa_args[@]}" "$vfa_image" python -m installer.cli --image "$vfa_image" --expected-revision "$vfa_revision" --expected-image-digest "$vfa_digest" "$@"
if [[ -f "$vfa_root/open-browser" && "$(<"$vfa_root/open-browser")" == 'http://127.0.0.1:4173' ]]; then
  if command -v open >/dev/null 2>&1; then open 'http://127.0.0.1:4173';
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open 'http://127.0.0.1:4173'; fi
fi
