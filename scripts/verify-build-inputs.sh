#!/usr/bin/env bash
# No installation, Docker, network, credential access, or source writes.
set -euo pipefail
vfa_verify_root="$(cd "$1" && pwd -P)"
vfa_verify_scope=(src apps contracts installer scripts alembic zk runtime pyproject.toml .dockerignore)
if [[ -e "$vfa_verify_root/.git" ]]; then
  command -v git >/dev/null || { printf '%s\n' 'BUILD_INPUT_GIT_REQUIRED'; exit 1; }
  git -C "$vfa_verify_root" diff --quiet HEAD -- "${vfa_verify_scope[@]}" || {
    printf '%s\n' 'BUILD_INPUT_DIRTY'; exit 1;
  }
  [[ -z "$(git -C "$vfa_verify_root" ls-files --others --exclude-standard -- "${vfa_verify_scope[@]}")" ]] || {
    printf '%s\n' 'BUILD_INPUT_UNDECLARED'; exit 1;
  }
  printf '%s\n' 'BUILD_INPUTS = REVIEWED_GIT'; exit 0
fi
vfa_verify_manifest="$vfa_verify_root/evaluator-build-inputs.sha256"
[[ -f "$vfa_verify_manifest" && ! -L "$vfa_verify_manifest" ]] || {
  printf '%s\n' 'BUILD_INPUT_MANIFEST_REQUIRED'; exit 1;
}
vfa_verify_count=0
while IFS= read -r vfa_verify_line; do
  vfa_verify_hash="${vfa_verify_line:0:64}"
  vfa_verify_path="${vfa_verify_line:66}"
  [[ "$vfa_verify_hash" =~ ^[a-f0-9]{64}$ && "${vfa_verify_line:64:2}" == '  ' \
    && "$vfa_verify_path" =~ ^[A-Za-z0-9_./-]+$ && "$vfa_verify_path" != /* \
    && "/$vfa_verify_path/" != *'/../'* && "/$vfa_verify_path/" != *'/./'* \
    && "$vfa_verify_path" != *'//'* ]] || { printf '%s\n' 'BUILD_INPUT_PATH_UNSAFE'; exit 1; }
  vfa_verify_file="$vfa_verify_root/$vfa_verify_path"
  [[ -f "$vfa_verify_file" && ! -L "$vfa_verify_file" ]] || { printf '%s\n' 'BUILD_INPUT_MISSING'; exit 1; }
  vfa_verify_parent="$(cd "$(dirname "$vfa_verify_file")" && pwd -P)"
  [[ "$vfa_verify_parent" == "$vfa_verify_root" || "$vfa_verify_parent" == "$vfa_verify_root/"* ]] || exit 1
  if command -v shasum >/dev/null 2>&1; then
    vfa_verify_actual="$(shasum -a 256 "$vfa_verify_file")"
  else
    vfa_verify_actual="$(sha256sum "$vfa_verify_file")"
  fi
  [[ "${vfa_verify_actual:0:64}" == "$vfa_verify_hash" ]] || { printf '%s\n' 'BUILD_INPUT_CONTENT_MISMATCH'; exit 1; }
  vfa_verify_count=$((vfa_verify_count + 1))
done < "$vfa_verify_manifest"
[[ "$vfa_verify_count" -gt 0 ]] || { printf '%s\n' 'BUILD_INPUT_MANIFEST_EMPTY'; exit 1; }
for vfa_verify_dir in src apps installer scripts contracts alembic zk runtime; do
  [[ ! -d "$vfa_verify_root/$vfa_verify_dir" ]] && continue
  while IFS= read -r vfa_verify_file; do
    vfa_verify_relative="${vfa_verify_file#"$vfa_verify_root/"}"
    awk -v path="$vfa_verify_relative" '$0 == substr($0,1,64) "  " path { found=1 } END { exit !found }' \
      "$vfa_verify_manifest" || { printf '%s\n' 'BUILD_INPUT_UNDECLARED'; exit 1; }
  done < <(find "$vfa_verify_root/$vfa_verify_dir" \
    -type d \( -name __pycache__ -o -name node_modules -o -name dist \) -prune -o -type f -print)
done
printf '%s\n' 'BUILD_INPUTS = MANIFEST_VERIFIED'
