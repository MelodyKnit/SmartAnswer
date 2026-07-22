#!/usr/bin/env bash
# GitHub Actions 在每次正式发布后通过 SSH 调用本脚本。
# 它不是常驻更新器：不安装 systemd 单元、不保留 GitHub 凭据，也不运行于业务容器内。

set -euo pipefail

readonly SERVICE_NAME="study-qb-assistant"

project_dir="${1:-}"
image_ref="${2:-}"
version="${3:-}"
build_sha="${4:-}"
health_base_url="${5:-}"
ghcr_username="${6:-}"
compose_file=""
candidate_compose_file=""

fail() {
  printf 'Release deployment failed: %s\n' "$1" >&2
  exit 1
}

validate_arguments() {
  [[ "$project_dir" =~ ^/[A-Za-z0-9._/-]+$ ]] || fail "invalid project directory"
  [[ "$image_ref" =~ ^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[a-f0-9]{64}$ ]] || fail "invalid image reference"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "invalid release version"
  [[ "$build_sha" =~ ^[a-f0-9]{40}$ ]] || fail "invalid build revision"
  [[ "$health_base_url" =~ ^https?://127\.0\.0\.1:[1-9][0-9]{0,4}$ ]] || fail "invalid health URL"
  [[ "$ghcr_username" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "invalid GHCR username"
  compose_file="$project_dir/docker-compose.yaml"
  candidate_compose_file="$project_dir/deploy/docker-compose.release.yaml"
  [[ -f "$compose_file" ]] || fail "docker-compose.yaml is missing"
  [[ -f "$candidate_compose_file" ]] || fail "release Compose file is missing"
}

wait_until_healthy() {
  local expected_version="$1"
  local attempt health_payload version_payload

  for attempt in $(seq 1 45); do
    health_payload="$(curl --fail --silent --show-error "$health_base_url/api/v1/healthz" 2>/dev/null || true)"
    version_payload="$(curl --fail --silent --show-error "$health_base_url/api/v1/version" 2>/dev/null || true)"
    if [[ "$health_payload" == *'"ok":true'* ]] && [[ "$version_payload" == *"\"version\":\"$expected_version\""* ]]; then
      return 0
    fi
    sleep 2
  done

  return 1
}

write_release_environment() {
  local target="$1"
  local temporary

  umask 077
  temporary="$(mktemp "$project_dir/.env.release.XXXXXX")"
  printf 'STQB_IMAGE_REF=%s\nSTQB_RELEASE_VERSION=%s\nSTQB_RELEASE_SHA=%s\n' \
    "$image_ref" "$version" "$build_sha" > "$temporary"
  mv "$temporary" "$target"
}

replace_file_atomically() {
  local source="$1"
  local target="$2"
  local mode="$3"
  local temporary

  temporary="$(mktemp "$(dirname "$target")/.${target##*/}.XXXXXX")"
  install -m "$mode" "$source" "$temporary"
  mv "$temporary" "$target"
}

backup_database() {
  local database_path="$project_dir/deploy-data/runtime/study-qb.sqlite3"
  local backup_directory="$project_dir/deploy-data/backups/releases/$(date -u +%Y%m%dT%H%M%SZ)-$version"
  local backup_path="$backup_directory/study-qb.sqlite3"
  local container_backup_path="/app/data/backups/releases/$(basename "$backup_directory")/study-qb.sqlite3"

  [[ -f "$database_path" ]] || return 0
  mkdir -p "$backup_directory"

  if docker inspect --format '{{.State.Running}}' "$SERVICE_NAME" 2>/dev/null | grep -qx true; then
    docker exec "$SERVICE_NAME" mkdir -p "$(dirname "$container_backup_path")"
    docker exec "$SERVICE_NAME" python -c \
      'import sqlite3, sys; source = sqlite3.connect("/app/data/runtime/study-qb.sqlite3"); target = sqlite3.connect(sys.argv[1]); source.backup(target); target.close(); source.close()' \
      "$container_backup_path"
  else
    cp "$database_path" "$backup_path"
  fi

  printf '%s\n' "$backup_path"
}

restore_previous_release() {
  local release_env="$1"
  local previous_env="$2"
  local had_previous_release="$3"
  local backup_path="$4"
  local previous_version="$5"

  replace_file_atomically "$previous_compose" "$compose_file" 644

  if [[ "$had_previous_release" != true ]]; then
    rm -f "$release_env"
    printf 'Original Compose file restored, but no prior release is available to restart.\n' >&2
    return 1
  fi

  install -m 600 "$previous_env" "$release_env"
  docker compose --env-file "$release_env" -f "$compose_file" stop "$SERVICE_NAME" || true

  if [[ -n "$backup_path" && -f "$backup_path" ]]; then
    local database_path="$project_dir/deploy-data/runtime/study-qb.sqlite3"
    rm -f "${database_path}-wal" "${database_path}-shm"
    cp "$backup_path" "$database_path"
  fi

  docker compose --env-file "$release_env" -f "$compose_file" up -d --no-build "$SERVICE_NAME"
  [[ -z "$previous_version" ]] || wait_until_healthy "$previous_version"
}

validate_arguments

IFS= read -r ghcr_read_token || fail "missing GHCR read token"
[[ -n "$ghcr_read_token" ]] || fail "missing GHCR read token"

release_env="$project_dir/.env.release"
previous_env="$(mktemp)"
previous_compose="$(mktemp)"
docker_config="$(mktemp -d)"
had_previous_release=false
backup_path=""
previous_version=""

cleanup() {
  rm -f "$previous_env"
  rm -f "$previous_compose" "$candidate_compose_file"
  rm -rf "$docker_config"
}
trap cleanup EXIT

if [[ -f "$release_env" ]]; then
  cp "$release_env" "$previous_env"
  had_previous_release=true
  previous_version="$(awk -F= '$1 == "STQB_RELEASE_VERSION" { print $2; exit }' "$release_env")"
fi
cp "$compose_file" "$previous_compose"

printf '%s' "$ghcr_read_token" | docker --config "$docker_config" login ghcr.io -u "$ghcr_username" --password-stdin >/dev/null
docker --config "$docker_config" pull "$image_ref"
docker --config "$docker_config" logout ghcr.io >/dev/null 2>&1 || true
unset ghcr_read_token

candidate_build="$(docker run --rm --entrypoint python "$image_ref" -c 'from study_qb_assistant.version import BUILD_INFO; print(BUILD_INFO.version + ":" + BUILD_INFO.build_sha)')"
[[ "$candidate_build" == "$version:$build_sha" ]] || fail "image build metadata does not match release"

backup_path="$(backup_database)" || fail "SQLite backup failed; deployment was not started"
write_release_environment "$release_env"
replace_file_atomically "$candidate_compose_file" "$compose_file" 644

if ! docker compose --env-file "$release_env" -f "$compose_file" up -d --no-build "$SERVICE_NAME"; then
  if ! restore_previous_release "$release_env" "$previous_env" "$had_previous_release" "$backup_path" "$previous_version"; then
    fail "Compose start failed and rollback failed"
  fi
  fail "Compose start failed; previous release was restored"
fi

if ! wait_until_healthy "$version"; then
  if ! restore_previous_release "$release_env" "$previous_env" "$had_previous_release" "$backup_path" "$previous_version"; then
    fail "health check failed and rollback failed"
  fi
  fail "health check failed; previous release was restored"
fi

printf 'Release %s deployed successfully.\n' "$version"
