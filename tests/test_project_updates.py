"""项目内 GitHub Release 更新控制面的回归测试。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, RLock
from typing import Any, Callable

import httpx
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402
from study_qb_assistant.platform.updates.contracts import (  # noqa: E402
    ProjectUpdateError,
    ProjectUpdateRelease,
)
from study_qb_assistant.platform.updates.github import (  # noqa: E402
    GitHubProjectUpdateGateway,
    project_release_from_payload,
)
from study_qb_assistant.platform.updates.monitor import ProjectUpdateMonitor  # noqa: E402
from study_qb_assistant.platform.updates.service import (  # noqa: E402
    WORKFLOW_START_TIMEOUT_SECONDS,
    ProjectUpdateService,
)
from study_qb_assistant.questions.models import CanonicalQuestionRecord  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.version import BuildInfo  # noqa: E402


class FakeProjectUpdateGateway:
    """无需真实 GitHub 网络的更新网关替身。"""

    def __init__(self) -> None:
        self.release = ProjectUpdateRelease(
            version="0.1.33",
            tag="v0.1.33",
            name="v0.1.33",
            body="测试发布说明",
            published_at="2026-07-20T10:00:00Z",
            html_url="https://github.com/example/study-qb/releases/tag/v0.1.33",
            image="ghcr.io/example/study-qb",
            image_digest="sha256:" + "a" * 64,
            build_sha="b" * 40,
        )
        self.dispatches: list[dict[str, str]] = []
        self.run: dict[str, Any] | None = None
        self.release_error: ProjectUpdateError | None = None

    def latest_release(self, repository: str, token: str) -> ProjectUpdateRelease:
        assert repository == "example/study-qb"
        assert token == "github-test-token"
        if self.release_error is not None:
            raise self.release_error
        return self.release

    def dispatch_deployment(
        self,
        repository: str,
        workflow: str,
        token: str,
        *,
        release_tag: str,
        operation_id: str,
    ) -> None:
        self.dispatches.append(
            {
                "repository": repository,
                "workflow": workflow,
                "token": token,
                "release_tag": release_tag,
                "operation_id": operation_id,
            }
        )

    def find_deployment_run(
        self,
        repository: str,
        workflow: str,
        token: str,
        operation_id: str,
    ) -> dict[str, Any] | None:
        if self.run is None:
            return None
        return self.run if operation_id in str(self.run.get("display_title") or "") else None

    def get_deployment_run(
        self, repository: str, token: str, workflow_run_id: int
    ) -> dict[str, Any]:
        assert repository == "example/study-qb"
        assert token == "github-test-token"
        assert self.run is not None
        assert workflow_run_id == self.run["id"]
        return self.run


class ProjectUpdateTests(unittest.TestCase):
    """验证配置、Release 校验和 Actions 调度形成完整闭环。"""

    def test_update_configuration_masks_token_and_requires_complete_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, platform, headers, _ = self.create_client(Path(directory))

            rejected = client.patch(
                "/api/v1/system-config",
                json={"project_update_enabled": "true"},
                headers=headers,
            )
            saved = client.patch(
                "/api/v1/system-config",
                json={
                    "project_update_enabled": "true",
                    "project_update_repository": "https://github.com/example/study-qb.git",
                    "project_update_workflow": "deploy-release.yml",
                    "project_update_github_token": "github-test-token",
                },
                headers=headers,
            )
            visible = client.get("/api/v1/system-config", headers=headers)
            stored_token = platform.settings.get_system_config(reveal_secret=True)[
                "project_update_github_token"
            ]

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["config"]["project_update_repository"], "example/study-qb")
        self.assertNotIn("project_update_github_token", saved.json()["config"])
        self.assertTrue(saved.json()["config"]["project_update_github_token_configured"])
        self.assertNotIn("project_update_github_token", visible.json()["config"])
        self.assertEqual(stored_token, "github-test-token")

    def test_check_dispatch_and_poll_update_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, gateway = self.create_client(Path(directory))
            configured = client.patch(
                "/api/v1/system-config",
                json={
                    "project_update_enabled": "true",
                    "project_update_repository": "example/study-qb",
                    "project_update_workflow": "deploy-release.yml",
                    "project_update_github_token": "github-test-token",
                },
                headers=headers,
            )
            checked = client.post("/api/v1/project-update/check", headers=headers)
            dispatched = client.post(
                "/api/v1/project-update/apply",
                json={"expected_version": "0.1.33"},
                headers=headers,
            )
            operation_id = dispatched.json()["operation"]["operation_id"]
            gateway.run = {
                "id": 881,
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/example/study-qb/actions/runs/881",
                "display_title": f"Deploy v0.1.33 · {operation_id}",
            }
            completed = client.get(
                f"/api/v1/project-update/operations/{operation_id}", headers=headers
            )

        self.assertEqual(configured.status_code, 200)
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json()["update"]["has_update"])
        self.assertEqual(dispatched.status_code, 202)
        self.assertEqual(gateway.dispatches[0]["release_tag"], "v0.1.33")
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["operation"]["state"], "succeeded")
        self.assertEqual(completed.json()["operation"]["workflow_run_id"], 881)

    def test_manifest_mismatch_is_rejected_before_deployment(self) -> None:
        release = {"name": "v0.1.33", "body": "", "published_at": "", "html_url": ""}
        manifest = {
            "schema_version": 1,
            "repository": "other/repository",
            "version": "0.1.33",
            "tag": "v0.1.33",
            "image": "ghcr.io/other/repository",
            "image_digest": "sha256:" + "a" * 64,
            "commit_sha": "b" * 40,
        }

        with self.assertRaisesRegex(ProjectUpdateError, "不一致"):
            project_release_from_payload("example/study-qb", release, manifest, "0.1.33", "v0.1.33")

    def test_private_release_manifest_uses_github_asset_authentication(self) -> None:
        """私有仓库的 manifest 必须经 GitHub 资产 API 和 Bearer 令牌读取。"""

        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/releases/latest"):
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "tag_name": "v0.1.33",
                        "name": "v0.1.33",
                        "body": "",
                        "published_at": "2026-07-20T10:00:00Z",
                        "html_url": "https://github.com/example/study-qb/releases/tag/v0.1.33",
                        "assets": [
                            {
                                "name": "release-manifest.json",
                                "url": "https://api.github.com/repos/example/study-qb/releases/assets/1",
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                request=request,
                json={
                    "schema_version": 1,
                    "repository": "example/study-qb",
                    "version": "0.1.33",
                    "tag": "v0.1.33",
                    "image": "ghcr.io/example/study-qb",
                    "image_digest": "sha256:" + "a" * 64,
                    "commit_sha": "b" * 40,
                },
            )

        gateway = GitHubProjectUpdateGateway(
            client=httpx.Client(transport=httpx.MockTransport(handle))
        )
        release = gateway.latest_release("example/study-qb", "private-token")

        self.assertEqual(release.version, "0.1.33")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1].headers["Authorization"], "Bearer private-token")
        self.assertEqual(requests[1].headers["Accept"], "application/octet-stream")

    def test_background_check_and_missing_workflow_timeout_recover_for_retry(self) -> None:
        """自动巡检应检查新版本，并回收长期没有工作流的排队任务。"""

        now = [1_000.0]
        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, gateway = self.create_client(
                Path(directory), clock=lambda: now[0]
            )
            configured = client.patch(
                "/api/v1/system-config",
                json={
                    "project_update_enabled": "true",
                    "project_update_auto_check_enabled": "true",
                    "project_update_check_interval_hours": "1",
                    "project_update_repository": "example/study-qb",
                    "project_update_workflow": "deploy-release.yml",
                    "project_update_github_token": "github-test-token",
                },
                headers=headers,
            )
            service = client.app.state.services.updates
            service.background_cycle()
            has_update = bool(service.status()["has_update"])
            operation = service.apply(expected_version="0.1.33", requested_by="owner")
            now[0] += WORKFLOW_START_TIMEOUT_SECONDS + 1
            service.background_cycle()
            recovered = service.operation(operation.operation_id)

        self.assertEqual(configured.status_code, 200)
        self.assertTrue(has_update)
        self.assertEqual(gateway.dispatches[0]["release_tag"], "v0.1.33")
        self.assertEqual(recovered.state, "failed")
        self.assertEqual(recovered.error, "PROJECT_UPDATE_WORKFLOW_NOT_STARTED")

    def test_token_can_only_be_cleared_after_update_is_disabled(self) -> None:
        """显式清除令牌不能留下启用但无凭据的更新配置。"""

        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, _ = self.create_client(Path(directory))
            client.patch(
                "/api/v1/system-config",
                json={
                    "project_update_enabled": "true",
                    "project_update_repository": "example/study-qb",
                    "project_update_workflow": "deploy-release.yml",
                    "project_update_github_token": "github-test-token",
                },
                headers=headers,
            )
            rejected = client.delete("/api/v1/project-update/token", headers=headers)
            disabled = client.patch(
                "/api/v1/system-config",
                json={"project_update_enabled": "false"},
                headers=headers,
            )
            cleared = client.delete("/api/v1/project-update/token", headers=headers)

        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(cleared.json()["config"]["project_update_github_token_configured"])

    def test_completed_operation_remains_readable_after_token_is_cleared(self) -> None:
        """清除令牌不应破坏已完成任务的历史状态读取。"""

        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, gateway = self.create_client(Path(directory))
            client.patch(
                "/api/v1/system-config",
                json={
                    "project_update_enabled": "true",
                    "project_update_repository": "example/study-qb",
                    "project_update_workflow": "deploy-release.yml",
                    "project_update_github_token": "github-test-token",
                },
                headers=headers,
            )
            dispatched = client.post(
                "/api/v1/project-update/apply",
                json={"expected_version": "0.1.33"},
                headers=headers,
            )
            operation_id = dispatched.json()["operation"]["operation_id"]
            gateway.run = {
                "id": 881,
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/example/study-qb/actions/runs/881",
                "display_title": f"Deploy v0.1.33 · {operation_id}",
            }
            client.get(f"/api/v1/project-update/operations/{operation_id}", headers=headers)
            client.patch(
                "/api/v1/system-config",
                json={"project_update_enabled": "false"},
                headers=headers,
            )
            client.delete("/api/v1/project-update/token", headers=headers)
            historical = client.get(
                f"/api/v1/project-update/operations/{operation_id}", headers=headers
            )

        self.assertEqual(historical.status_code, 200)
        self.assertEqual(historical.json()["operation"]["state"], "succeeded")

    def test_check_failure_keeps_last_verified_release_summary(self) -> None:
        """网络失败只更新错误状态，不能丢失上次校验过的候选 Release。"""

        with tempfile.TemporaryDirectory() as directory:
            client, _, headers, gateway = self.create_client(Path(directory))
            client.patch(
                "/api/v1/system-config",
                json={
                    "project_update_enabled": "true",
                    "project_update_repository": "example/study-qb",
                    "project_update_workflow": "deploy-release.yml",
                    "project_update_github_token": "github-test-token",
                },
                headers=headers,
            )
            client.post("/api/v1/project-update/check", headers=headers)
            gateway.release_error = ProjectUpdateError(
                "PROJECT_UPDATE_GITHUB_UNAVAILABLE",
                "无法连接 GitHub，请检查网络或代理配置",
                http_status=503,
            )
            failed = client.post("/api/v1/project-update/check", headers=headers)
            status = client.get("/api/v1/project-update/status", headers=headers)

        self.assertEqual(failed.status_code, 503)
        self.assertEqual(status.json()["update"]["latest_version"], "0.1.33")
        self.assertTrue(status.json()["update"]["has_update"])

    def create_client(
        self, directory: Path, *, clock: Callable[[], float] | None = None
    ) -> tuple[TestClient, PlatformServices, dict[str, str], FakeProjectUpdateGateway]:
        database_path = directory / "runtime" / "study-qb.sqlite3"
        auth = AuthService(database_path)
        platform = PlatformServices(database_path)
        gateway = FakeProjectUpdateGateway()
        platform.updates = ProjectUpdateService(
            platform.settings.repository,
            platform.settings,
            RLock(),
            gateway=gateway,
            build_info=BuildInfo(version="0.1.32", build_sha="c" * 40, build_type="release"),
            clock=clock or time.time,
        )
        client = TestClient(
            create_app(
                sample_index(), auth_service=auth, platform_services=platform, require_auth=True
            )
        )
        client.post("/api/v1/auth/register", json={"username": "owner", "password": "password123"})
        login = client.post("/api/v1/auth/login", json={"username": "owner", "password": "password123"})
        return client, platform, {"Authorization": f"Bearer {login.json()['token']}"}, gateway


class ProjectUpdateMonitorTests(unittest.IsolatedAsyncioTestCase):
    """验证真实运行时使用的后台巡检生命周期。"""

    async def test_monitor_runs_one_cycle_and_stops_cleanly(self) -> None:
        """巡检应调用服务且停止后释放内部任务状态。"""

        service = CountingUpdateService()
        monitor = ProjectUpdateMonitor(service, tick_seconds=0.01)

        await monitor.start()
        await asyncio.wait_for(asyncio.to_thread(service.called.wait), timeout=1)
        await monitor.stop()

        self.assertGreaterEqual(service.calls, 1)
        self.assertIsNone(monitor.task)
        self.assertIsNone(monitor.stop_event)


class CountingUpdateService:
    """只用于验证后台巡检的同步服务替身。"""

    def __init__(self) -> None:
        self.calls = 0
        self.called = Event()

    def background_cycle(self) -> None:
        self.calls += 1
        self.called.set()


def sample_index() -> LocalQuestionIndex:
    """构造不依赖外部数据文件的最小题库。"""

    return LocalQuestionIndex(
        (
            CanonicalQuestionRecord(
                question_id="project-update:sample",
                title_raw="项目更新测试题",
                question_type="single",
                options_raw=("A. 正确", "B. 错误"),
                answer_raw="A",
                explanation="",
                subject="test",
                chapter=None,
                tags=("project-update",),
                source_name="test",
                source_url="",
                source_license="test-only",
                source_split="active",
                source_record_path="",
            ),
        )
    )


if __name__ == "__main__":
    unittest.main()
