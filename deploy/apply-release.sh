#!/usr/bin/env bash
# Apply one already-validated release locally on the deployment host.
# The pull/update wrapper supplies the immutable image reference; this script
# owns the local Compose switch, data backup, health check and rollback.

set -euo pipefail

readonly SERVICE_NAME="study-qb-assistant"
readonly CONTAINER_DATA_DIR="/app/data"
readonly REMOTE_IMAGE_RE='^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[a-f0-9]{64}$'
readonly LOCAL_IMAGE_RE='^stqb-local/smartanswer:release-[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{12}$'

project_dir="${1:-}"
image_ref="${2:-}"
version="${3:-}"
build_sha="${4:-}"
health_base_url="${5:-}"
release_image_ref="${6:-$image_ref}"
backup_keep="${7:-${STQB_RELEASE_BACKUP_KEEP:-2}}"
compose_file=""
candidate_compose_file=""
local_override_file=""
image_override_file=""
release_env=""
database_path=""
database_container_path=""
database_mode="sqlite"
image_source=""

fail() {
  printf 'Release deployment failed: %s\n' "$1" >&2
  exit 1
}

validate_arguments() {
  local actual_docker_context expected_docker_context backup_keep_number

  [[ "$project_dir" =~ ^/[A-Za-z0-9._/-]+$ ]] || fail "invalid project directory"
  if [[ "$image_ref" =~ $REMOTE_IMAGE_RE ]]; then
    image_source="remote"
  elif [[ "$image_ref" =~ $LOCAL_IMAGE_RE ]]; then
    image_source="local"
  else
    fail "invalid image reference"
  fi
  [[ "$release_image_ref" =~ $REMOTE_IMAGE_RE ]] || fail "invalid release image reference"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "invalid release version"
  [[ "$build_sha" =~ ^[a-f0-9]{40}$ ]] || fail "invalid build revision"
  [[ "$backup_keep" =~ ^[0-9]{1,3}$ ]] || fail "invalid release backup retention count"
  backup_keep_number=$((10#$backup_keep))
  (( backup_keep_number >= 1 && backup_keep_number <= 100 )) || fail "release backup retention count must be between 1 and 100"
  backup_keep="$backup_keep_number"
  [[ "$health_base_url" =~ ^https?://127\.0\.0\.1:[1-9][0-9]{0,4}$ ]] || fail "invalid health URL"
  command -v docker >/dev/null 2>&1 || fail "docker command is unavailable"

  expected_docker_context="${STQB_DEPLOY_DOCKER_CONTEXT:-${STQB_DOCKER_CONTEXT:-rootless}}"
  [[ "$expected_docker_context" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid Docker context"
  actual_docker_context="$(docker context show 2>/dev/null || true)"
  [[ "$actual_docker_context" == "$expected_docker_context" ]] || fail "Docker context must be $expected_docker_context, got ${actual_docker_context:-none}"

  compose_file="$project_dir/docker-compose.yaml"
  candidate_compose_file="$project_dir/deploy/docker-compose.release.yaml"
  local_override_file="$project_dir/docker-compose.override.yml"
  image_override_file="$project_dir/deploy/docker-compose.release-image.yaml"
  release_env="$project_dir/.env.release"
  [[ -d "$project_dir" ]] || fail "project directory is missing"
  [[ -f "$candidate_compose_file" ]] || fail "release Compose file is missing"
}

compose_with_file() {
  local selected_compose_file="$1"
  shift
  local -a compose_arguments=(
    --env-file "$release_env"
    -f "$selected_compose_file"
  )

  # 服务器覆盖文件只承载端口、网络和本机服务等运维差异，发布镜像由最后一层覆盖强制指定。
  if [[ -f "$local_override_file" ]]; then
    compose_arguments+=(-f "$local_override_file")
  fi
  if [[ -f "$image_override_file" ]]; then
    compose_arguments+=(-f "$image_override_file")
  fi

  (
    cd "$project_dir" || fail "project directory is unavailable"
    docker compose "${compose_arguments[@]}" "$@"
  )
}

compose_current_release() {
  compose_with_file "$compose_file" "$@"
}

service_is_running() {
  docker inspect --format '{{.State.Running}}' "$SERVICE_NAME" 2>/dev/null | grep -qx true
}

resolve_database_paths() {
  local configured_path database_relative_path

  database_mode="sqlite"
  database_relative_path="runtime/study-qb.sqlite3"

  if service_is_running; then
    configured_path="$(docker exec "$SERVICE_NAME" python -c '
from study_qb_assistant.config import get_global_config
config = get_global_config()
print("external" if config.database_url.strip() else config.database_path_resolved)
')"
    configured_path="${configured_path//$'\r'/}"
    if [[ "$configured_path" == "external" ]]; then
      database_mode="external"
      database_path=""
      database_container_path=""
      printf 'External database detected; SQLite snapshot skipped.\n' >&2
      return 0
    fi
    [[ "$configured_path" == "$CONTAINER_DATA_DIR/"* ]] || fail "SQLite database is outside the data mount"
    database_relative_path="${configured_path#"$CONTAINER_DATA_DIR"/}"
  fi

  [[ "$database_relative_path" =~ ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ ]] || fail "invalid SQLite database path"
  database_path="$project_dir/deploy-data/$database_relative_path"
  database_container_path="$CONTAINER_DATA_DIR/$database_relative_path"
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
  printf 'STQB_IMAGE_REF=%s\nSTQB_RELEASE_IMAGE_REF=%s\nSTQB_RELEASE_VERSION=%s\nSTQB_RELEASE_SHA=%s\n' \
    "$image_ref" "$release_image_ref" "$version" "$build_sha" > "$temporary"
  mv "$temporary" "$target"
}

write_release_image_override() {
  local target="$1"
  local temporary

  temporary="$(mktemp "$(dirname "$target")/.${target##*/}.XXXXXX")"
  cat > "$temporary" <<'EOF'
services:
  study-qb-assistant:
    image: ${STQB_IMAGE_REF:?STQB_IMAGE_REF is required for a release deployment}
EOF
  chmod 644 "$temporary"
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
  local backup_directory backup_path container_backup_path

  [[ "$database_mode" == "sqlite" ]] || return 0
  backup_directory="$project_dir/deploy-data/backups/releases/$(date -u +%Y%m%dT%H%M%SZ)-$version"
  backup_path="$backup_directory/$(basename "$database_path")"
  container_backup_path="$CONTAINER_DATA_DIR/backups/releases/$(basename "$backup_directory")/$(basename "$database_path")"
  if [[ ! -f "$database_path" ]]; then
    if service_is_running; then
      fail "configured SQLite database is missing from the data mount"
    fi
    return 0
  fi
  mkdir -p "$backup_directory" || return 1
  touch "$backup_directory/.incomplete" || return 1

  if service_is_running; then
    docker exec "$SERVICE_NAME" mkdir -p "$(dirname "$container_backup_path")" || return 1
    docker exec "$SERVICE_NAME" python -c \
      'import sqlite3, sys; source = sqlite3.connect(sys.argv[1]); target = sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()' \
      "$database_container_path" \
      "$container_backup_path" || return 1
  else
    cp "$database_path" "$backup_path" || return 1
  fi

  [[ -s "$backup_path" ]] || fail "SQLite backup was not written to the data mount"
  rm -f "$backup_directory/.incomplete" || return 1

  printf '%s\n' "$backup_path"
}

cleanup_release_backups() {
  local backup_root="$project_dir/deploy-data/backups/releases"
  local project_real backup_root_real name backup_path size_line size_kb command_name listing
  local retained_count deleted_count=0 index freed_kb=0
  local -a candidates=()

  [[ -d "$backup_root" ]] || return 0
  for command_name in find sort du; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      printf 'Release backup cleanup skipped: command is unavailable: %s.\n' "$command_name" >&2
      return 1
    fi
  done
  for backup_path in "$project_dir/deploy-data" "$project_dir/deploy-data/backups" "$backup_root"; do
    [[ ! -L "$backup_path" ]] || { printf 'Release backup cleanup refused: symlink in backup path.\n' >&2; return 1; }
  done
  project_real="$(cd "$project_dir" && pwd -P)" || return 1
  backup_root_real="$(cd "$backup_root" 2>/dev/null && pwd -P)" || return 1
  [[ "$backup_root_real" == "$project_real/deploy-data/backups/releases" ]] || {
    printf 'Release backup cleanup skipped: resolved path is outside the configured backup root.\n' >&2
    return 1
  }

  listing="$(find "$backup_root_real" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort -r)" || return 1
  while IFS= read -r name; do
    [[ "$name" =~ ^[0-9]{8}T[0-9]{6}Z-v?[0-9]+\.[0-9]+\.[0-9]+(-manual)?$ ]] || continue
    [[ ! -e "$backup_root_real/$name/.incomplete" ]] || continue
    [[ -n "$(find "$backup_root_real/$name" -maxdepth 1 -type f -size +0c \( -name '*.sqlite3' -o -name '*.sqlite' -o -name '*.db' \) -print -quit)" ]] || continue
    candidates+=("$name")
  done <<< "$listing"

  retained_count=${#candidates[@]}
  (( retained_count <= backup_keep )) || retained_count="$backup_keep"
  for ((index = retained_count; index < ${#candidates[@]}; index++)); do
    name="${candidates[$index]}"
    backup_path="$backup_root_real/$name"
    [[ -d "$backup_path" && ! -L "$backup_path" ]] || continue
    size_line="$(du -sk -- "$backup_path" 2>/dev/null)" || {
      printf 'Release backup cleanup skipped: cannot measure %s.\n' "$name" >&2
      return 1
    }
    size_kb="${size_line%%$'\t'*}"
    [[ "$size_kb" =~ ^[0-9]+$ ]] || return 1
    rm -rf --one-file-system -- "$backup_path" || {
      printf 'Release backup cleanup failed while removing %s.\n' "$name" >&2
      return 1
    }
    freed_kb=$((freed_kb + size_kb))
    deleted_count=$((deleted_count + 1))
  done
  printf 'Release backup retention: kept=%s deleted=%s freed_mb=%s\n' \
    "$retained_count" \
    "$deleted_count" \
    "$((freed_kb / 1024))" >&2
}

capture_unmanaged_release() {
  local running_image running_build running_version running_sha

  [[ "$had_previous_release" != true ]] || return 0
  service_is_running || return 0

  running_image="$(docker inspect --format '{{.Config.Image}}' "$SERVICE_NAME")"
  running_build="$(docker exec "$SERVICE_NAME" python -c '
from study_qb_assistant.version import BUILD_INFO
print(f"{BUILD_INFO.version}:{BUILD_INFO.build_sha}")
')"
  [[ "$running_image" != "" ]] || fail "running container image is unavailable"
  [[ "$running_build" =~ ^([0-9]+\.[0-9]+\.[0-9]+):([a-f0-9]{40})$ ]] || fail "running container build metadata is unavailable"

  running_version="${BASH_REMATCH[1]}"
  running_sha="${BASH_REMATCH[2]}"
  previous_version="$running_version"
  printf 'STQB_IMAGE_REF=%s\nSTQB_RELEASE_VERSION=%s\nSTQB_RELEASE_SHA=%s\n' \
    "$running_image" "$running_version" "$running_sha" > "$previous_env"
  had_previous_release=true
  previous_release_is_unmanaged=true
  printf 'Existing unmanaged release detected; it will be retained as rollback target.\n' >&2
}

restore_release_metadata_without_restart() {
  if [[ "$had_previous_release" == true && "$previous_release_is_unmanaged" != true ]]; then
    install -m 600 "$previous_env" "$release_env"
    write_release_image_override "$image_override_file"
    return 0
  fi

  rm -f "$release_env" "$image_override_file"
}

restore_previous_release() {
  local had_previous_compose="$1"
  local backup_path="$2"

  if [[ "$had_previous_compose" == true ]]; then
    replace_file_atomically "$previous_compose" "$compose_file" 644
  else
    rm -f "$compose_file"
  fi

  if [[ "$had_previous_release" != true ]]; then
    rm -f "$release_env" "$image_override_file"
    docker rm -f "$SERVICE_NAME" >/dev/null 2>&1 || true
    printf 'No prior release is available to restart.\n' >&2
    return 1
  fi

  install -m 600 "$previous_env" "$release_env"
  write_release_image_override "$image_override_file"
  compose_current_release stop "$SERVICE_NAME" || true

  if [[ "$database_mode" == "sqlite" && -n "$backup_path" && -f "$backup_path" ]]; then
    rm -f "${database_path}-wal" "${database_path}-shm"
    cp "$backup_path" "$database_path"
  fi

  compose_current_release up -d --no-build "$SERVICE_NAME"
  [[ -z "$previous_version" ]] || wait_until_healthy "$previous_version"

  # 首次纳入受控发布前可能没有 .env.release；回滚后恢复服务器原有的无托管状态。
  if [[ "$previous_release_is_unmanaged" == true ]]; then
    rm -f "$release_env" "$image_override_file"
  fi
}

validate_arguments

previous_env="$(mktemp)"
previous_compose="$(mktemp)"
had_previous_release=false
previous_release_is_unmanaged=false
had_previous_compose=false
backup_path=""
previous_version=""

cleanup() {
  rm -f "$previous_env"
  rm -f "$previous_compose" "$candidate_compose_file"
}
trap cleanup EXIT

if [[ -f "$release_env" ]]; then
  cp "$release_env" "$previous_env"
  had_previous_release=true
  previous_version="$(awk -F= '$1 == "STQB_RELEASE_VERSION" { print $2; exit }' "$release_env")"
fi
if [[ -f "$compose_file" ]]; then
  cp "$compose_file" "$previous_compose"
  had_previous_compose=true
fi
capture_unmanaged_release

# Prefer the immutable registry image. The updater may supply a locally built
# image only after it has validated the exact Release source commit.
if [[ "$image_source" == "remote" ]]; then
  docker pull "$image_ref"
else
  docker image inspect "$image_ref" >/dev/null 2>&1 || fail "local fallback image is unavailable"
fi

candidate_build="$(docker run --rm --entrypoint python "$image_ref" -c 'from study_qb_assistant.version import BUILD_INFO; print(BUILD_INFO.version + ":" + BUILD_INFO.build_sha)')"
[[ "$candidate_build" == "$version:$build_sha" ]] || fail "image build metadata does not match release"

resolve_database_paths
write_release_environment "$release_env"
write_release_image_override "$image_override_file"
if ! compose_with_file "$candidate_compose_file" config -q; then
  restore_release_metadata_without_restart
  fail "candidate Compose configuration is invalid"
fi

if ! backup_path="$(backup_database)"; then
  restore_release_metadata_without_restart
  fail "SQLite backup failed; deployment was not started"
fi
replace_file_atomically "$candidate_compose_file" "$compose_file" 644

if ! compose_current_release up -d --no-build "$SERVICE_NAME"; then
  if ! restore_previous_release "$had_previous_compose" "$backup_path"; then
    fail "Compose start failed and rollback failed"
  fi
  fail "Compose start failed; previous release was restored"
fi

if ! wait_until_healthy "$version"; then
  if ! restore_previous_release "$had_previous_compose" "$backup_path"; then
    fail "health check failed and rollback failed"
  fi
  fail "health check failed; previous release was restored"
fi

if [[ "$had_previous_release" == true ]]; then
  replace_file_atomically "$previous_env" "$project_dir/.env.release.previous" 600
fi
if [[ "$had_previous_compose" == true ]]; then
  replace_file_atomically "$previous_compose" "$project_dir/deploy/docker-compose.previous.yaml" 644
fi
if ! cleanup_release_backups; then
  printf 'Warning: release is healthy, but backup retention cleanup was incomplete.\n' >&2
fi

printf 'Release %s deployed successfully.\n' "$version"
