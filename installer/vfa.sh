#!/usr/bin/env bash
set -euo pipefail
vfa_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
vfa_image=vfa-evaluator:source
[[ ! -f "$vfa_root/image" ]] || vfa_image="$(<"$vfa_root/image")"
[[ "$vfa_image" =~ ^vfa-evaluator:[a-zA-Z0-9._-]+$ ]] || exit 1
docker info >/dev/null 2>&1 || { printf '%s\n' 'DOCKER_NOT_RUNNING: Start Docker Desktop, then run vfa start.'; exit 1; }
vfa_args=(run --rm -i)
# Piped public bootstrap must acquire its credential terminal, not consume script stdin.
if [[ ! -t 0 && -r /dev/tty ]]; then exec </dev/tty; fi
[[ ! -t 0 ]] || vfa_args+=(-t)
vfa_args+=(-v /var/run/docker.sock:/var/run/docker.sock -v "$vfa_root:/install" -e "VFA_HOST_ROOT=$vfa_root")
[[ ! -d "$HOME/Downloads" ]] || vfa_args+=(-v "$HOME/Downloads:/credentials/downloads:ro")
[[ ! -d "$HOME/Desktop" ]] || vfa_args+=(-v "$HOME/Desktop:/credentials/desktop:ro")
docker "${vfa_args[@]}" "$vfa_image" python -m installer.cli "$@"
if [[ -f "$vfa_root/open-browser" && "$(<"$vfa_root/open-browser")" == 'http://127.0.0.1:4173' ]]; then
  open 'http://127.0.0.1:4173'
fi
