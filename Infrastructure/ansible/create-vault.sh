#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly VAULT_PATH="${SCRIPT_DIR}/vault.yml"

for command in ansible-vault python3 git; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

if [[ -e "${VAULT_PATH}" ]]; then
  echo "Refusing to overwrite existing Vault: ${VAULT_PATH}" >&2
  exit 1
fi

if ! git -C "${WORKSPACE_ROOT}" check-ignore -q \
  "Infrastructure/ansible/vault.yml"; then
  echo "Refusing to create an unignored secrets file." >&2
  exit 1
fi

prompt_optional() {
  local prompt="$1"
  local value=""
  read -r -p "${prompt}: " value
  printf '%s' "${value}"
}

expand_home_path() {
  local value="$1"
  case "${value}" in
    "~")
      printf '%s' "${HOME}"
      ;;
    "~/"*)
      printf '%s/%s' "${HOME}" "${value:2}"
      ;;
    *)
      printf '%s' "${value}"
      ;;
  esac
}

yaml_string() {
  python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))'
}

write_value() {
  local key="$1"
  local value="$2"
  printf '%s: %s\n' "${key}" "$(printf '%s' "${value}" | yaml_string)"
}

echo "This creates Infrastructure/ansible/vault.yml and encrypts it in place."
echo "Secret values are entered locally and are not printed."
echo

chaos_public_key="$(
  expand_home_path "$(prompt_optional "Chaos cleaner public key path (optional)")"
)"
if [[ -n "${chaos_public_key}" && ! -f "${chaos_public_key}" ]]; then
  echo "Key file does not exist: ${chaos_public_key}" >&2
  exit 1
fi

plaintext_path="$(mktemp "${TMPDIR:-/tmp}/agents-vault.XXXXXX")"
cleanup() {
  rm -f "${plaintext_path}"
}
trap cleanup EXIT INT TERM

{
  echo "---"
  write_value "vault_chaos_cleaner_public_key_file" "${chaos_public_key}"
} >"${plaintext_path}"

echo
echo "Enter and confirm a new Ansible Vault password."
ansible-vault encrypt "${plaintext_path}" --output "${VAULT_PATH}"
chmod 600 "${VAULT_PATH}"

echo "Created encrypted Vault: ${VAULT_PATH}"
echo "Keep the Vault password outside this repository."
