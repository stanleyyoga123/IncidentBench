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

prompt_required() {
  local prompt="$1"
  local value=""
  while [[ -z "${value}" ]]; do
    read -r -p "${prompt}: " value
  done
  printf '%s' "${value}"
}

prompt_optional() {
  local prompt="$1"
  local value=""
  read -r -p "${prompt}: " value
  printf '%s' "${value}"
}

prompt_secret_optional() {
  local prompt="$1"
  local value=""
  read -r -s -p "${prompt}: " value
  echo >&2
  printf '%s' "${value}"
}

prompt_secret_required() {
  local prompt="$1"
  local value=""
  while [[ -z "${value}" ]]; do
    read -r -s -p "${prompt}: " value
    echo >&2
  done
  printf '%s' "${value}"
}

random_secret() {
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
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

llm_url="$(prompt_required "OpenAI-compatible LLM endpoint")"
llm_token="$(prompt_secret_optional "LLM API token (leave empty to use EMPTY)")"
llm_token="${llm_token:-EMPTY}"

langfuse_base_url="$(prompt_optional "Langfuse base URL (optional)")"
langfuse_public_key=""
langfuse_secret_key=""
if [[ -n "${langfuse_base_url}" ]]; then
  langfuse_public_key="$(prompt_secret_required "Langfuse public key")"
  langfuse_secret_key="$(prompt_secret_required "Langfuse secret key")"
fi

chaos_public_key="$(
  expand_home_path "$(prompt_optional "Chaos cleaner public key path (optional)")"
)"
chaos_private_key="$(
  expand_home_path "$(prompt_optional "Chaos cleaner private key path (optional)")"
)"
if { [[ -n "${chaos_public_key}" ]] && [[ -z "${chaos_private_key}" ]]; } ||
  { [[ -z "${chaos_public_key}" ]] && [[ -n "${chaos_private_key}" ]]; }; then
  echo "Supply both chaos cleaner key paths or leave both empty." >&2
  exit 1
fi
for key_path in "${chaos_public_key}" "${chaos_private_key}"; do
  if [[ -n "${key_path}" && ! -f "${key_path}" ]]; then
    echo "Key file does not exist: ${key_path}" >&2
    exit 1
  fi
done

evaluation_s3_uri="$(prompt_optional "Evaluation S3 URI (optional)")"
evaluation_aws_access_key_id=""
evaluation_aws_secret_access_key=""
if [[ -n "${evaluation_s3_uri}" ]]; then
  evaluation_aws_access_key_id="$(
    prompt_secret_required "Evaluation AWS access key ID"
  )"
  evaluation_aws_secret_access_key="$(
    prompt_secret_required "Evaluation AWS secret access key"
  )"
fi

plaintext_path="$(mktemp "${TMPDIR:-/tmp}/agents-vault.XXXXXX")"
cleanup() {
  rm -f "${plaintext_path}"
}
trap cleanup EXIT INT TERM

{
  echo "---"
  write_value "vault_database_password" "$(random_secret)"
  write_value "vault_detector_profile_api_token" "$(random_secret)"
  write_value "vault_agent_ingestion_token" "$(random_secret)"
  write_value "vault_agent_control_token" "$(random_secret)"
  write_value "vault_rca_submit_token" "$(random_secret)"
  write_value "vault_remediator_submit_token" "$(random_secret)"
  write_value "vault_mcp_investigation_token" "$(random_secret)"
  write_value "vault_mcp_remediation_token" "$(random_secret)"
  write_value "vault_agent_llm_url" "${llm_url}"
  write_value "vault_agent_llm_token" "${llm_token}"
  write_value "vault_langfuse_base_url" "${langfuse_base_url}"
  write_value "vault_langfuse_public_key" "${langfuse_public_key}"
  write_value "vault_langfuse_secret_key" "${langfuse_secret_key}"
  write_value "vault_chaos_cleaner_public_key_file" "${chaos_public_key}"
  write_value "vault_chaos_cleaner_private_key_file" "${chaos_private_key}"
  write_value "vault_evaluation_s3_uri" "${evaluation_s3_uri}"
  write_value "vault_evaluation_aws_access_key_id" \
    "${evaluation_aws_access_key_id}"
  write_value "vault_evaluation_aws_secret_access_key" \
    "${evaluation_aws_secret_access_key}"
} >"${plaintext_path}"

echo
echo "Enter and confirm a new Ansible Vault password."
ansible-vault encrypt "${plaintext_path}" --output "${VAULT_PATH}"
chmod 600 "${VAULT_PATH}"

echo "Created encrypted Vault: ${VAULT_PATH}"
echo "Keep the Vault password outside this repository."
