#!/usr/bin/env bash
# Pull and apply the newest validated GitHub Release on the deployment host.
# This script runs locally on each server; it never connects to a central host.

set -euo pipefail

readonly DEFAULT_SOURCE_REPOSITORY="MelodyKnit/SmartAnswer"
readonly DEFAULT_GITHUB_API_URL="https://api.github.com"
readonly DEFAULT_HEALTH_URL="http://127.0.0.1:3003"
readonly DEFAULT_DOCKER_CONTEXT="rootless"
readonly DEFAULT_PLATFORM="linux/amd64"
readonly DEFAULT_SOURCE_FALLBACK="true"
readonly DEFAULT_RELEASE_BACKUP_KEEP="2"
readonly DEFAULT_RELEASE_IMAGE_KEEP="2"

cleanup_only=false
cleanup_preview=false
if [[ "${1:-}" == "--cleanup-only" ]]; then
  cleanup_only=true
  shift
elif [[ "${1:-}" == "--cleanup-preview" ]]; then
  cleanup_only=true
  cleanup_preview=true
  shift
fi
config_file="${1:-${STQB_UPDATE_CONFIG:-}}"
project_dir=""
source_repository=""
github_api_url=""
health_url=""
docker_context=""
platform=""
allow_downgrade=""
allow_source_fallback=""
release_tag=""
github_token_file=""
ghcr_username=""
ghcr_token_file=""
release_backup_keep=""
release_image_keep=""
release_image_repository=""
current_runtime_image_ref=""
current_release_image_ref=""
current_version=""
current_image_ref=""
previous_runtime_image_ref=""
previous_release_image_ref=""
stage_dir=""
auth_header_file=""
lock_file=""

fail() {
  printf 'Release update failed: %s\n' "$1" >&2
  exit 1
}

log() {
  printf 'Release update: %s\n' "$1"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

if [[ -z "$config_file" || ! -f "$config_file" ]]; then
  fail "an update config file is required; pass it as the first argument (after --cleanup-only when used)"
fi
if [[ "$cleanup_only" == true && "$#" -gt 1 ]]; then
  fail "cleanup-only accepts exactly one update config file"
fi

# The config is an operator-owned local file and is never downloaded from GitHub.
# shellcheck disable=SC1090
source "$config_file"

project_dir="${STQB_PROJECT_DIR:-}"
source_repository="${STQB_SOURCE_REPOSITORY:-$DEFAULT_SOURCE_REPOSITORY}"
github_api_url="${STQB_GITHUB_API_URL:-$DEFAULT_GITHUB_API_URL}"
health_url="${STQB_HEALTH_URL:-$DEFAULT_HEALTH_URL}"
docker_context="${STQB_DOCKER_CONTEXT:-$DEFAULT_DOCKER_CONTEXT}"
platform="${STQB_PLATFORM:-$DEFAULT_PLATFORM}"
allow_downgrade="${STQB_ALLOW_DOWNGRADE:-false}"
allow_source_fallback="${STQB_ALLOW_SOURCE_FALLBACK:-$DEFAULT_SOURCE_FALLBACK}"
release_tag="${STQB_RELEASE_TAG:-}"
github_token_file="${STQB_GITHUB_TOKEN_FILE:-}"
ghcr_username="${STQB_GHCR_USERNAME:-}"
ghcr_token_file="${STQB_GHCR_TOKEN_FILE:-}"
release_backup_keep="${STQB_RELEASE_BACKUP_KEEP:-$DEFAULT_RELEASE_BACKUP_KEEP}"
release_image_keep="${STQB_RELEASE_IMAGE_KEEP:-$DEFAULT_RELEASE_IMAGE_KEEP}"

[[ "$project_dir" =~ ^/[A-Za-z0-9._/-]+$ && "$project_dir" != "/" && -d "$project_dir" ]] || fail "STQB_PROJECT_DIR must point to an existing absolute project directory"
[[ "$source_repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "invalid STQB_SOURCE_REPOSITORY"
[[ "$github_api_url" =~ ^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._/-]+)?$ ]] || fail "invalid STQB_GITHUB_API_URL"
github_api_url="${github_api_url%/}"
[[ "$health_url" =~ ^https?://127\.0\.0\.1:[1-9][0-9]{0,4}$ ]] || fail "invalid STQB_HEALTH_URL"
[[ "$docker_context" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid STQB_DOCKER_CONTEXT"
[[ "$platform" =~ ^[A-Za-z0-9._/-]+$ ]] || fail "invalid STQB_PLATFORM"
[[ "$allow_downgrade" == "true" || "$allow_downgrade" == "false" ]] || fail "STQB_ALLOW_DOWNGRADE must be true or false"
[[ "$allow_source_fallback" == "true" || "$allow_source_fallback" == "false" ]] || fail "STQB_ALLOW_SOURCE_FALLBACK must be true or false"
[[ "$release_backup_keep" =~ ^[0-9]{1,3}$ ]] || fail "STQB_RELEASE_BACKUP_KEEP must be between 1 and 100"
release_backup_keep_number=$((10#$release_backup_keep))
(( release_backup_keep_number >= 1 && release_backup_keep_number <= 100 )) || fail "STQB_RELEASE_BACKUP_KEEP must be between 1 and 100"
release_backup_keep="$release_backup_keep_number"
[[ "$release_image_keep" =~ ^[0-9]{1,2}$ ]] || fail "STQB_RELEASE_IMAGE_KEEP must be between 2 and 20"
release_image_keep_number=$((10#$release_image_keep))
(( release_image_keep_number >= 2 && release_image_keep_number <= 20 )) || fail "STQB_RELEASE_IMAGE_KEEP must be between 2 and 20"
release_image_keep="$release_image_keep_number"
if [[ -n "$release_tag" ]]; then
  [[ "$release_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "invalid STQB_RELEASE_TAG"
fi

require_command bash
require_command docker
require_command flock
require_command python3
require_command find
require_command sort
require_command du

if [[ "$cleanup_only" != true && -n "$github_token_file" ]]; then
  [[ -r "$github_token_file" ]] || fail "STQB_GITHUB_TOKEN_FILE is not readable"
fi
if [[ "$cleanup_only" != true && -n "$ghcr_token_file" ]]; then
  [[ -r "$ghcr_token_file" ]] || fail "STQB_GHCR_TOKEN_FILE is not readable"
  [[ -n "$ghcr_username" ]] || fail "STQB_GHCR_USERNAME is required with STQB_GHCR_TOKEN_FILE"
fi

load_current_release() {
  local current_env="$project_dir/.env.release"
  local previous_env="$project_dir/.env.release.previous"

  [[ -f "$current_env" ]] || return 0
  current_version="$(awk -F= '$1 == "STQB_RELEASE_VERSION" { print $2; exit }' "$current_env" | tr -d '\r')"
  current_runtime_image_ref="$(awk -F= '$1 == "STQB_IMAGE_REF" { print $2; exit }' "$current_env" | tr -d '\r')"
  current_release_image_ref="$(awk -F= '$1 == "STQB_RELEASE_IMAGE_REF" { print $2; exit }' "$current_env" | tr -d '\r')"
  current_image_ref="$current_release_image_ref"
  [[ -n "$current_image_ref" ]] || current_image_ref="$current_runtime_image_ref"
  if [[ -f "$previous_env" ]]; then
    previous_runtime_image_ref="$(awk -F= '$1 == "STQB_IMAGE_REF" { print $2; exit }' "$previous_env" | tr -d '\r')"
    previous_release_image_ref="$(awk -F= '$1 == "STQB_RELEASE_IMAGE_REF" { print $2; exit }' "$previous_env" | tr -d '\r')"
  fi
}

cleanup_release_backups() {
  local backup_root="$project_dir/deploy-data/backups/releases"
  local project_real backup_root_real name backup_path size_line size_kb listing
  local retained_count deleted_count=0 index freed_kb=0
  local -a candidates=()

  [[ -d "$backup_root" ]] || {
    log "release backup cleanup: no snapshots found"
    return 0
  }
  for backup_path in "$project_dir/deploy-data" "$project_dir/deploy-data/backups" "$backup_root"; do
    [[ ! -L "$backup_path" ]] || { log "release backup cleanup refused: symlink in backup path"; return 1; }
  done
  project_real="$(cd "$project_dir" && pwd -P)" || return 1
  backup_root_real="$(cd "$backup_root" 2>/dev/null && pwd -P)" || {
    log "release backup cleanup failed: backup directory is unavailable"
    return 1
  }
  if [[ "$backup_root_real" != "$project_real/deploy-data/backups/releases" ]]; then
    log "release backup cleanup refused: resolved path differs from the configured release directory"
    return 1
  fi

  listing="$(find "$backup_root_real" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort -r)" || return 1
  while IFS= read -r name; do
    [[ "$name" =~ ^[0-9]{8}T[0-9]{6}Z-v?[0-9]+\.[0-9]+\.[0-9]+(-manual)?$ ]] || continue
    [[ ! -e "$backup_root_real/$name/.incomplete" ]] || continue
    [[ -n "$(find "$backup_root_real/$name" -maxdepth 1 -type f -size +0c \( -name '*.sqlite3' -o -name '*.sqlite' -o -name '*.db' \) -print -quit)" ]] || continue
    candidates+=("$name")
  done <<< "$listing"

  retained_count=${#candidates[@]}
  (( retained_count <= release_backup_keep )) || retained_count="$release_backup_keep"
  for ((index = retained_count; index < ${#candidates[@]}; index++)); do
    name="${candidates[$index]}"
    backup_path="$backup_root_real/$name"
    [[ -d "$backup_path" && ! -L "$backup_path" ]] || continue
    size_line="$(du -sk -- "$backup_path" 2>/dev/null)" || {
      log "release backup cleanup failed: unable to measure snapshot $name"
      return 1
    }
    size_kb="${size_line%%[[:space:]]*}"
    [[ "$size_kb" =~ ^[0-9]+$ ]] || {
      log "release backup cleanup failed: invalid size for snapshot $name"
      return 1
    }
    if [[ "$cleanup_preview" == true ]]; then
      log "would remove release snapshot: $name size_mb=$((size_kb / 1024))"
    elif ! rm -rf --one-file-system -- "$backup_path"; then
      log "release backup cleanup failed while removing snapshot $name"
      return 1
    fi
    freed_kb=$((freed_kb + size_kb))
    deleted_count=$((deleted_count + 1))
  done
  log "release backup cleanup: kept=$retained_count removed_or_planned=$deleted_count size_mb=$((freed_kb / 1024)) preview=$cleanup_preview"
}

cleanup_release_images() {
  local image_listing active_image_id current_ref_id image_id repository tag digest image_ref row containers used source
  local id removed=0 skipped=0
  local -a rows=() ordered_ids=()
  local -A refs_by_id=() seen_ids=() keep_ids=() excluded_ids=() rollback_ids=()

  image_listing="$(docker image ls --digests --no-trunc --format '{{.Repository}} {{.Tag}} {{.Digest}} {{.ID}}')" || {
    log "release image cleanup skipped: Docker image listing failed"
    return 1
  }
  active_image_id="$(docker inspect --format '{{.Image}}' study-qb-assistant 2>/dev/null || true)"
  containers="$(docker container ls -aq)" || return 1
  if [[ -n "$containers" ]]; then
    local -a container_ids=()
    mapfile -t container_ids <<< "$containers"
    used="$(docker inspect --format '{{.Image}}' "${container_ids[@]}")" || return 1
    while IFS= read -r id; do
      [[ "$id" =~ ^sha256:[a-f0-9]{64}$ ]] || return 1
      keep_ids["$id"]=1
    done <<< "$used"
  fi
  mapfile -t rows <<< "$image_listing"

  for row in "${rows[@]}"; do
    read -r repository tag digest image_id <<< "$row"
    [[ -n "$repository" && "$image_id" =~ ^sha256:[a-f0-9]{64}$ ]] || continue
    if [[ "$repository" == "$release_image_repository" ]]; then
      if [[ "$tag" != "<none>" && ! "$tag" =~ ^(v?[0-9]+\.[0-9]+\.[0-9]+|stable)$ ]]; then
        excluded_ids["$image_id"]=1
        continue
      fi
      if [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
        image_ref="$repository@$digest"
      elif [[ "$tag" =~ ^(v?[0-9]+\.[0-9]+\.[0-9]+|stable)$ ]]; then
        image_ref="$repository:$tag"
      else
        continue
      fi
    elif [[ "$repository" == "stqb-local/smartanswer" && "$tag" =~ ^release-[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{12}$ ]]; then
      source="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$image_id")" || return 1
      if [[ "${source,,}" != "https://github.com/${source_repository,,}" ]]; then
        excluded_ids["$image_id"]=1
        continue
      fi
      image_ref="$repository:$tag"
    else
      excluded_ids["$image_id"]=1
      continue
    fi
    if [[ -n "${refs_by_id[$image_id]+present}" ]]; then
      refs_by_id["$image_id"]+=$'\n'"$image_ref"
    else
      refs_by_id["$image_id"]="$image_ref"
      ordered_ids+=("$image_id")
    fi
    if [[ "$repository" == "$release_image_repository" && "$tag" != "<none>" ]]; then
      refs_by_id["$image_id"]+=$'\n'"$repository:$tag"
    fi
  done

  if [[ -n "$active_image_id" && -n "${refs_by_id[$active_image_id]+present}" ]]; then
    keep_ids["$active_image_id"]=1
    rollback_ids["$active_image_id"]=1
  fi
  for image_ref in "$current_runtime_image_ref" "$current_release_image_ref" "$previous_runtime_image_ref" "$previous_release_image_ref"; do
    [[ -n "$image_ref" ]] || continue
    current_ref_id="$(docker image inspect --format '{{.Id}}' "$image_ref" 2>/dev/null || true)"
    if [[ -n "$current_ref_id" && -n "${refs_by_id[$current_ref_id]+present}" ]]; then
      keep_ids["$current_ref_id"]=1
      rollback_ids["$current_ref_id"]=1
    fi
  done
  local retained=0 window_count=0
  for id in "${ordered_ids[@]}"; do
    [[ -z "${rollback_ids[$id]+present}" ]] || window_count=$((window_count + 1))
  done
  if ((${#ordered_ids[@]} > 0 && window_count == 0)); then
    log "release image cleanup refused: current application image cannot be identified"
    return 1
  fi
  for id in "${ordered_ids[@]}"; do
    [[ -n "${seen_ids[$id]+present}" ]] && continue
    seen_ids["$id"]=1
    [[ -n "${keep_ids[$id]+present}" ]] && continue
    if ((window_count < release_image_keep)); then
      keep_ids["$id"]=1
      rollback_ids["$id"]=1
      window_count=$((window_count + 1))
    fi
  done

  for id in "${ordered_ids[@]}"; do
    if [[ -n "${keep_ids[$id]+present}" || -n "${excluded_ids[$id]+present}" ]]; then
      retained=$((retained + 1))
      continue
    fi
    while IFS= read -r image_ref; do
      [[ -n "$image_ref" ]] || continue
      if [[ "$cleanup_preview" == true ]]; then
        log "would remove image reference: $image_ref"
        continue
      fi
      if docker image rm "$image_ref" >/dev/null 2>&1; then
        removed=$((removed + 1))
      else
        skipped=$((skipped + 1))
        log "release image cleanup could not remove $image_ref; it may still be in use"
      fi
    done <<< "${refs_by_id[$id]}"
  done
  log "release image cleanup: retained=$retained removed_refs=$removed skipped_refs=$skipped"
}

mkdir -p "$project_dir/deploy"
lock_file="${STQB_UPDATE_LOCK_FILE:-$project_dir/deploy/.update.lock}"
exec 9>"$lock_file"
flock -n 9 || {
  log "another update is already running; skipping"
  exit 0
}

actual_docker_context="$(docker context show 2>/dev/null || true)"
[[ "$actual_docker_context" == "$docker_context" ]] || fail "Docker context must be $docker_context, got ${actual_docker_context:-none}"
load_current_release
release_image_repository="ghcr.io/${source_repository,,}"
free_bytes_before="$(python3 -c 'import shutil, sys; print(shutil.disk_usage(sys.argv[1]).free)' "$project_dir")"
cleanup_release_backups || fail "release backup cleanup failed; update stopped before image pull"
cleanup_release_images || fail "release image cleanup failed; update stopped before image pull"
free_bytes_after="$(python3 -c 'import shutil, sys; print(shutil.disk_usage(sys.argv[1]).free)' "$project_dir")"
log "storage after cleanup: free_mb=$((free_bytes_after / 1048576)) change_mb=$(((free_bytes_after - free_bytes_before) / 1048576))"
if [[ "$cleanup_only" == true ]]; then
  log "storage maintenance completed (preview=$cleanup_preview)"
  exit 0
fi

require_command curl
require_command tar

stage_dir="$(mktemp -d "${TMPDIR:-/tmp}/stqb-update.XXXXXX")"
cleanup() {
  rm -rf "$stage_dir"
}
trap cleanup EXIT

declare -a curl_auth_args=()
if [[ -n "$github_token_file" ]]; then
  auth_header_file="$stage_dir/github-auth.header"
  token="$(tr -d '\r\n' < "$github_token_file")"
  [[ -n "$token" && "$token" != *[[:space:]]* ]] || fail "GitHub token file is empty or malformed"
  printf 'Authorization: Bearer %s\n' "$token" > "$auth_header_file"
  chmod 600 "$auth_header_file"
  curl_auth_args+=(--header "@$auth_header_file")
fi

github_get() {
  local accept="$1"
  local url="$2"
  curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --connect-timeout 10 \
    --max-time 60 \
    --header "Accept: $accept" \
    --header 'User-Agent: StudyQuestionBankAssistant-release-updater' \
    "${curl_auth_args[@]}" \
    "$url"
}

install_atomic() {
  local source="$1"
  local target="$2"
  local mode="$3"
  local temporary

  temporary="$(mktemp "$(dirname "$target")/.${target##*/}.XXXXXX")"
  install -m "$mode" "$source" "$temporary"
  mv -f "$temporary" "$target"
}

repository_api_url="$github_api_url/repos/$source_repository"
release_endpoint="$repository_api_url/releases/latest"
if [[ -n "$release_tag" ]]; then
  release_endpoint="$repository_api_url/releases/tags/$release_tag"
fi

release_json="$stage_dir/release.json"
if ! github_get 'application/vnd.github+json' "$release_endpoint" > "$release_json"; then
  fail "unable to read GitHub Release metadata"
fi

release_metadata="$(python3 - "$release_json" "$github_api_url" <<'PY'
import json
import sys

path, api_url = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

if payload.get("draft") or payload.get("prerelease"):
    raise SystemExit("latest release is not a stable published release")
tag = str(payload.get("tag_name") or "")
assets = payload.get("assets")
if not isinstance(assets, list):
    raise SystemExit("release assets are missing")
manifest_url = ""
for asset in assets:
    if isinstance(asset, dict) and asset.get("name") == "release-manifest.json":
        manifest_url = str(asset.get("url") or "")
        break
if not manifest_url.startswith(api_url + "/repos/"):
    raise SystemExit("release manifest URL is not a GitHub API asset URL")
print(f"{tag}\t{manifest_url}")
PY
)" || fail "invalid GitHub Release metadata"
IFS=$'\t' read -r resolved_release_tag manifest_url <<< "$release_metadata"
[[ "$resolved_release_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "GitHub Release tag is invalid"
if [[ -n "$release_tag" && "$resolved_release_tag" != "$release_tag" ]]; then
  fail "GitHub returned a different Release tag"
fi

manifest_json="$stage_dir/release-manifest.json"
if ! github_get 'application/octet-stream' "$manifest_url" > "$manifest_json"; then
  fail "unable to download release-manifest.json"
fi

manifest_values="$(python3 - "$manifest_json" "$source_repository" "$resolved_release_tag" "$platform" <<'PY'
import json
import re
import sys

path, repository, expected_tag, expected_platform = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

version = str(payload.get("version") or "")
tag = str(payload.get("tag") or "")
manifest_repository = str(payload.get("repository") or "")
image = str(payload.get("image") or "").lower()
digest = str(payload.get("image_digest") or "")
commit_sha = str(payload.get("commit_sha") or "").lower()
platform = str(payload.get("platform") or "")
expected_version = expected_tag.removeprefix("v")
expected_image = f"ghcr.io/{repository.lower()}"

if payload.get("schema_version") != 1:
    raise SystemExit("unsupported release manifest schema")
if tag != expected_tag or version != expected_version:
    raise SystemExit("release manifest tag and version do not match")
if manifest_repository.lower() != repository.lower():
    raise SystemExit("release manifest repository does not match local configuration")
if image != expected_image:
    raise SystemExit("release manifest image does not match local repository")
if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
    raise SystemExit("release manifest image digest is invalid")
if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
    raise SystemExit("release manifest commit SHA is invalid")
if platform != expected_platform:
    raise SystemExit("release manifest platform does not match local configuration")
print("\t".join((version, image, digest, commit_sha)))
PY
)" || fail "release manifest validation failed"
IFS=$'\t' read -r version image digest build_sha <<< "$manifest_values"
image_ref="$image@$digest"

release_decision="$(python3 - "$current_version" "$current_image_ref" "$version" "$image_ref" "$allow_downgrade" <<'PY'
import re
import sys

current_version, current_image, candidate_version, candidate_image, allow_downgrade = sys.argv[1:]
version_re = re.compile(r"^\d+\.\d+\.\d+$")

def parse(value: str) -> tuple[int, int, int]:
    if not version_re.fullmatch(value):
        raise SystemExit("current release version is invalid")
    return tuple(int(part) for part in value.split("."))

if not current_version:
    print("apply")
    raise SystemExit

current = parse(current_version)
candidate = parse(candidate_version)
if current == candidate:
    if current_image and current_image != candidate_image:
        raise SystemExit("same release version points to a different image digest")
    print("current")
elif current > candidate and allow_downgrade != "true":
    print("newer")
elif current > candidate:
    print("apply")
else:
    print("apply")
PY
)" || fail "current release comparison failed"

case "$release_decision" in
  current)
    log "already running $version"
    exit 0
    ;;
  newer)
    log "current version $current_version is newer than $version; skipping downgrade"
    exit 0
    ;;
  apply)
    ;;
  *)
    fail "unknown release decision"
    ;;
esac

candidate_compose="$stage_dir/docker-compose.yaml"
candidate_apply="$stage_dir/apply-release.sh"
candidate_updater="$stage_dir/update-from-github.sh"
source_archive="$stage_dir/source.tar.gz"
source_dir="$stage_dir/source"
if ! github_get 'application/vnd.github.raw' "$repository_api_url/contents/docker-compose.yaml?ref=$build_sha" > "$candidate_compose"; then
  fail "unable to download docker-compose.yaml from the release commit"
fi
if ! github_get 'application/vnd.github.raw' "$repository_api_url/contents/deploy/apply-release.sh?ref=$build_sha" > "$candidate_apply"; then
  fail "unable to download apply-release.sh from the release commit"
fi
if ! github_get 'application/vnd.github.raw' "$repository_api_url/contents/deploy/update-from-github.sh?ref=$build_sha" > "$candidate_updater"; then
  fail "unable to download update-from-github.sh from the release commit"
fi

[[ -s "$candidate_compose" ]] || fail "downloaded Compose file is empty"
grep -q 'STQB_IMAGE_REF' "$candidate_compose" || fail "downloaded Compose file does not require the release image"
grep -q 'study-qb-assistant' "$candidate_compose" || fail "downloaded Compose file does not define the application service"
bash -n "$candidate_apply" || fail "downloaded apply-release.sh has invalid shell syntax"
bash -n "$candidate_updater" || fail "downloaded update-from-github.sh has invalid shell syntax"
chmod 700 "$candidate_apply" "$candidate_updater"

if [[ -n "$ghcr_token_file" ]]; then
  log "logging in to GHCR using the local credential file"
  docker login ghcr.io --username "$ghcr_username" --password-stdin < "$ghcr_token_file" >/dev/null
fi

actual_docker_context="$(docker context show 2>/dev/null || true)"
[[ "$actual_docker_context" == "$docker_context" ]] || fail "Docker context must be $docker_context, got ${actual_docker_context:-none}"

candidate_image_ref="$image_ref"
if ! docker pull "$image_ref" >/dev/null 2>&1; then
  [[ "$allow_source_fallback" == "true" ]] || fail "release image is unavailable and source fallback is disabled"
  log "registry image is unavailable; building the validated Release source locally"
  if ! github_get 'application/vnd.github+json' "$github_api_url/repos/$source_repository/tarball/$build_sha" > "$source_archive"; then
    fail "unable to download the validated Release source archive"
  fi
  mkdir -p "$source_dir"
  tar -xzf "$source_archive" -C "$source_dir" --strip-components=1
  [[ -f "$source_dir/Dockerfile" && -f "$source_dir/docker-compose.yaml" ]] || fail "Release source archive is incomplete"
  local_tag="stqb-local/smartanswer:release-${version}-${build_sha:0:12}"
  docker build \
    --pull \
    --platform "$platform" \
    --build-arg "APP_VERSION=$version" \
    --build-arg "BUILD_SHA=$build_sha" \
    --build-arg "SOURCE_REPOSITORY=$source_repository" \
    --tag "$local_tag" \
    "$source_dir"
  candidate_image_ref="$local_tag"
fi

candidate_build="$(docker run --rm --entrypoint python "$candidate_image_ref" -c 'from study_qb_assistant.version import BUILD_INFO; print(BUILD_INFO.version + ":" + BUILD_INFO.build_sha)' 2>/dev/null || true)"
[[ "$candidate_build" == "$version:$build_sha" ]] || fail "candidate image build metadata does not match Release manifest"

candidate_compose_target="$project_dir/deploy/docker-compose.release.yaml"
install_atomic "$candidate_compose" "$candidate_compose_target" 0644
export STQB_DEPLOY_DOCKER_CONTEXT="$docker_context"
export STQB_RELEASE_BACKUP_KEEP="$release_backup_keep"

log "applying $resolved_release_tag ($digest)"
if ! bash "$candidate_apply" "$project_dir" "$candidate_image_ref" "$version" "$build_sha" "$health_url" "$image_ref" "$release_backup_keep"; then
  # apply-release.sh installs its own cleanup trap after argument validation;
  # remove the candidate here too when validation fails before that trap exists.
  rm -f "$candidate_compose_target"
  fail "candidate release was rejected or rolled back"
fi

install_atomic "$candidate_apply" "$project_dir/deploy/apply-release.sh" 0700
install_atomic "$candidate_updater" "$project_dir/deploy/update-from-github.sh" 0700
load_current_release
cleanup_release_backups || log "warning: backup retention cleanup after deployment was incomplete"
cleanup_release_images || log "warning: image retention cleanup after deployment was incomplete"
log "release $version deployed successfully"
