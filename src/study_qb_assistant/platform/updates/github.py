"""GitHub Release 与 Actions API 适配器。"""

from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from .contracts import (
    ProjectUpdateError,
    ProjectUpdateRelease,
    normalize_version,
)


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ProjectUpdateGateway(Protocol):
    """项目更新服务需要的 GitHub 网络能力。"""

    def latest_release(self, repository: str, token: str) -> ProjectUpdateRelease:
        """读取并校验最新正式 Release。"""

    def dispatch_deployment(
        self,
        repository: str,
        workflow: str,
        token: str,
        *,
        release_tag: str,
        operation_id: str,
    ) -> None:
        """发起部署指定 Release 的 GitHub Actions 工作流。"""

    def find_deployment_run(
        self,
        repository: str,
        workflow: str,
        token: str,
        operation_id: str,
    ) -> dict[str, Any] | None:
        """按系统生成的操作 ID 查找对应工作流运行。"""

    def get_deployment_run(
        self,
        repository: str,
        token: str,
        workflow_run_id: int,
    ) -> dict[str, Any]:
        """读取已经关联的 GitHub Actions 运行状态。"""


class GitHubProjectUpdateGateway:
    """使用 GitHub REST API 的项目更新网关。"""

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

    def latest_release(self, repository: str, token: str) -> ProjectUpdateRelease:
        """读取最新正式 Release，并校验其中不可变镜像清单。"""

        payload = self.request_json(
            "GET",
            f"/repos/{repository}/releases/latest",
            token=token,
            release_lookup=True,
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
                "该 Release 缺少 release-manifest.json，无法安全更新",
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
            token=token,
            accept="application/octet-stream",
        )
        return project_release_from_payload(repository, payload, manifest, version, tag)

    def dispatch_deployment(
        self,
        repository: str,
        workflow: str,
        token: str,
        *,
        release_tag: str,
        operation_id: str,
    ) -> None:
        """请求工作流部署一个已校验的 Release 标签。"""

        self.request_empty(
            "POST",
            f"/repos/{repository}/actions/workflows/{workflow}/dispatches",
            token=token,
            json={
                "ref": release_tag,
                "inputs": {
                    "release_tag": release_tag,
                    "operation_id": operation_id,
                },
            },
        )

    def find_deployment_run(
        self,
        repository: str,
        workflow: str,
        token: str,
        operation_id: str,
    ) -> dict[str, Any] | None:
        """查询包含操作 ID 的最新 workflow_dispatch 运行。"""

        payload = self.request_json(
            "GET",
            f"/repos/{repository}/actions/workflows/{workflow}/runs",
            token=token,
            params={"event": "workflow_dispatch", "per_page": "20"},
        )
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            return None
        for item in runs:
            if not isinstance(item, dict):
                continue
            display_title = str(item.get("display_title") or "")
            if operation_id in display_title:
                return item
        return None

    def get_deployment_run(
        self,
        repository: str,
        token: str,
        workflow_run_id: int,
    ) -> dict[str, Any]:
        """读取已经定位的工作流，避免高并发仓库中列表窗口漏掉旧运行。"""

        if workflow_run_id < 1:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_OPERATION_INVALID",
                "GitHub Actions 运行标识无效",
                http_status=400,
            )
        return self.request_json(
            "GET",
            f"/repos/{repository}/actions/runs/{workflow_run_id}",
            token=token,
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        token: str,
        release_lookup: bool = False,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """发送 GitHub API JSON 请求并映射安全的管理员错误。"""

        return self.request_json_url(
            f"{self.api_base_url}{path}",
            method=method,
            token=token,
            params=params,
            release_lookup=release_lookup,
        )

    def request_json_url(
        self,
        url: str,
        *,
        method: str = "GET",
        token: str,
        params: dict[str, str] | None = None,
        release_lookup: bool = False,
        accept: str | None = None,
    ) -> dict[str, Any]:
        """请求 JSON 下载资源；不记录令牌或完整上游响应。"""

        response = self.request(
            method,
            url,
            token=token,
            params=params,
            release_lookup=release_lookup,
            accept=accept,
        )
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

    def request_empty(
        self,
        method: str,
        path: str,
        *,
        token: str,
        json: dict[str, Any],
    ) -> None:
        """发送无响应体的 GitHub Actions 调度请求。"""

        self.request(method, f"{self.api_base_url}{path}", token=token, json=json)

    def request(
        self,
        method: str,
        url: str,
        *,
        token: str,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        release_lookup: bool = False,
        accept: str | None = None,
    ) -> httpx.Response:
        """执行受超时限制的 GitHub 请求。"""

        headers = {
            "Accept": accept or "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "StudyQuestionBankAssistant/ProjectUpdate",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            if self.client is not None:
                response = self.client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    follow_redirects=True,
                )
            else:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = client.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=json,
                    )
        except httpx.HTTPError as exc:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_UNAVAILABLE",
                "无法连接 GitHub，请检查网络或代理配置",
                http_status=503,
            ) from exc
        if response.status_code in {401, 403}:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_AUTH_FAILED",
                "GitHub 访问令牌无效、已过期或权限不足",
                http_status=400,
            )
        if response.status_code == 404:
            code = "PROJECT_UPDATE_RELEASE_NOT_FOUND" if release_lookup else "PROJECT_UPDATE_GITHUB_RESOURCE_NOT_FOUND"
            message = (
                "未找到可用的正式 GitHub Release"
                if release_lookup
                else "GitHub 仓库、工作流或部署资源不存在"
            )
            raise ProjectUpdateError(code, message, http_status=404)
        if response.status_code >= 400:
            raise ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_REQUEST_FAILED",
                f"GitHub 更新请求失败（HTTP {response.status_code}）",
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
    """验证 Release manifest 与当前配置仓库的一致性。"""

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
            "GitHub Release manifest 与当前项目配置不一致，已拒绝更新",
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
