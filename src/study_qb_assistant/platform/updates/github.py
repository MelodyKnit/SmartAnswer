"""公开 GitHub Release API 适配器。"""

from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from .contracts import ProjectUpdateError, ProjectUpdateRelease, normalize_version


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ProjectUpdateGateway(Protocol):
    """项目更新状态需要的公开 GitHub Release 查询能力。"""

    def latest_release(self, repository: str) -> ProjectUpdateRelease:
        """读取并校验最新正式 Release。"""


class GitHubProjectUpdateGateway:
    """使用匿名 GitHub REST API 查询公开 Release。"""

    def __init__(
        self,
        *,
        api_base_url: str = GITHUB_API_BASE_URL,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def latest_release(self, repository: str) -> ProjectUpdateRelease:
        """读取公开正式 Release，并校验其中的不可变镜像清单。"""

        payload = self.request_json(
            f"/repos/{repository}/releases/latest", release_lookup=True
        )
        if bool(payload.get("draft")) or bool(payload.get("prerelease")):
            raise ProjectUpdateError(
                "PROJECT_UPDATE_RELEASE_INVALID",
                "最新 GitHub Release 不是正式发布版本",
                http_status=502,
            )
        tag = str(payload.get("tag_name") or "").strip()
        try:
            version = normalize_version(tag)
        except ValueError as exc:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_RELEASE_INVALID",
                "GitHub Release 标签必须使用 vX.Y.Z 格式",
                http_status=502,
            ) from exc

        assets = payload.get("assets")
        if not isinstance(assets, list):
            assets = []
        manifest_asset = next(
            (
                item
                for item in assets
                if isinstance(item, dict) and item.get("name") == "release-manifest.json"
            ),
            None,
        )
        if manifest_asset is None:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_MANIFEST_MISSING",
                "该 Release 缺少 release-manifest.json，无法校验版本信息",
                http_status=502,
            )
        download_url = str(manifest_asset.get("url") or "").strip()
        expected_asset_prefix = f"{self.api_base_url}/repos/{repository}/releases/assets/"
        if not download_url.startswith(expected_asset_prefix):
            raise ProjectUpdateError(
                "PROJECT_UPDATE_MANIFEST_INVALID",
                "Release manifest 必须通过 GitHub 资产 API 下载",
                http_status=502,
            )
        manifest = self.request_json_url(
            download_url,
            accept="application/octet-stream",
        )
        return project_release_from_payload(repository, payload, manifest, version, tag)

    def request_json(
        self,
        path: str,
        *,
        release_lookup: bool = False,
    ) -> dict[str, Any]:
        """请求 GitHub API JSON 资源。"""

        return self.request_json_url(
            f"{self.api_base_url}{path}", release_lookup=release_lookup
        )

    def request_json_url(
        self,
        url: str,
        *,
        release_lookup: bool = False,
        accept: str | None = None,
    ) -> dict[str, Any]:
        """请求公开 JSON 资源，绝不携带 Authorization 请求头。"""

        response = self.request(url, release_lookup=release_lookup, accept=accept)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_RESPONSE_INVALID",
                "GitHub 返回了无法解析的更新数据",
                http_status=502,
            ) from exc
        if not isinstance(payload, dict):
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_RESPONSE_INVALID",
                "GitHub 返回的更新数据格式无效",
                http_status=502,
            )
        return payload

    def request(
        self,
        url: str,
        *,
        release_lookup: bool = False,
        accept: str | None = None,
    ) -> httpx.Response:
        """执行受超时限制的匿名 GitHub 请求。"""

        headers = {
            "Accept": accept or "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "StudyQuestionBankAssistant/ReleaseStatus",
        }
        try:
            if self.client is not None:
                response = self.client.get(url, headers=headers, follow_redirects=True)
            else:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_UNAVAILABLE",
                "无法连接 GitHub，请检查网络或代理配置",
                http_status=503,
            ) from exc
        if response.status_code in {401, 403}:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_ACCESS_FAILED",
                "无法访问公开 GitHub Release，请检查仓库可见性或 GitHub API 限流",
                http_status=503,
            )
        if response.status_code == 404:
            code = (
                "PROJECT_UPDATE_RELEASE_NOT_FOUND"
                if release_lookup
                else "PROJECT_UPDATE_GITHUB_RESOURCE_NOT_FOUND"
            )
            message = (
                "未找到可用的正式 GitHub Release"
                if release_lookup
                else "GitHub Release 资源不存在"
            )
            raise ProjectUpdateError(code, message, http_status=404)
        if response.status_code >= 400:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_REQUEST_FAILED",
                f"GitHub 更新查询失败（HTTP {response.status_code}）",
                http_status=502,
            )
        return response


def project_release_from_payload(
    repository: str,
    release: dict[str, Any],
    manifest: dict[str, Any],
    version: str,
    tag: str,
) -> ProjectUpdateRelease:
    """验证 Release manifest 与当前公开仓库的一致性。"""

    manifest_repository = str(manifest.get("repository") or "").strip()
    manifest_version = str(manifest.get("version") or "").strip()
    manifest_tag = str(manifest.get("tag") or "").strip()
    expected_image = f"ghcr.io/{repository.lower()}"
    image = str(manifest.get("image") or "").strip().lower()
    image_digest = str(manifest.get("image_digest") or "").strip().lower()
    build_sha = str(manifest.get("commit_sha") or "").strip().lower()
    if (
        safe_schema_version(manifest.get("schema_version")) != 1
        or manifest_repository.lower() != repository.lower()
        or manifest_version != version
        or manifest_tag != tag
        or image != expected_image
        or not DIGEST_RE.fullmatch(image_digest)
        or not SHA_RE.fullmatch(build_sha)
    ):
        raise ProjectUpdateError(
            "PROJECT_UPDATE_MANIFEST_INVALID",
            "GitHub Release manifest 与当前项目来源不一致",
            http_status=502,
        )
    return ProjectUpdateRelease(
        version=version,
        tag=tag,
        name=safe_text(release.get("name"), 200) or tag,
        body=safe_text(release.get("body"), 12000),
        published_at=safe_text(release.get("published_at"), 80),
        html_url=safe_https_url(release.get("html_url")),
        image=image,
        image_digest=image_digest,
        build_sha=build_sha,
    )


def safe_text(value: object, limit: int) -> str:
    """把上游文本收敛到显示与持久化可接受的长度。"""

    return str(value or "").strip()[:limit]


def safe_schema_version(value: object) -> int:
    """读取 manifest schema 版本，异常值视为不支持。"""

    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        return 0


def safe_https_url(value: object) -> str:
    """只接受 GitHub 提供的 HTTPS 链接。"""

    url = safe_text(value, 1000)
    return url if url.startswith("https://") else ""
