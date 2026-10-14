"""服务器本地 GitHub Release 拉取器回归测试。"""

from __future__ import annotations

import json
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tarfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPDATER_SCRIPT = PROJECT_ROOT / "deploy" / "update-from-github.sh"
NEW_VERSION = "0.7.0"
NEW_SHA = "a" * 40
NEW_DIGEST = "b" * 64
NEW_IMAGE = f"ghcr.io/melodyknit/smartanswer@sha256:{NEW_DIGEST}"
OLD_IMAGE = "ghcr.io/melodyknit/smartanswer@sha256:" + "c" * 64


def find_usable_bash() -> Path | None:
    """查找能直接执行脚本的 Bash，排除未安装发行版的 WSL 启动器。"""

    candidates: list[Path] = []
    discovered = shutil.which("bash")
    if discovered:
        candidates.append(Path(discovered))
    git_path = shutil.which("git")
    if git_path:
        git_root = Path(git_path).resolve().parent.parent
        candidates.extend((git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe"))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        completed = subprocess.run(
            [str(candidate), "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        if completed.returncode == 0:
            return candidate
    return None


class ReleaseUpdaterTests(unittest.TestCase):
    """验证服务器本地拉取、manifest 校验和幂等决策。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bash = find_usable_bash()
        if cls.bash is None:
            raise unittest.SkipTest("当前环境没有可用 Bash")

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.project_dir = self.root / "project"
        self.deploy_dir = self.project_dir / "deploy"
        self.fake_bin = self.root / "bin"
        self.project_dir.mkdir()
        self.deploy_dir.mkdir()
        self.fake_bin.mkdir()

        self.write_text(
            self.project_dir / "docker-compose.yaml",
            """services:
  study-qb-assistant:
    image: release-placeholder
# STQB_IMAGE_REF
""",
        )
        self.write_text(
            self.project_dir / ".env.release",
            chr(10).join(
                (
                    f"STQB_IMAGE_REF={OLD_IMAGE}",
                    "STQB_RELEASE_VERSION=0.6.0",
                    "STQB_RELEASE_SHA=" + "d" * 40,
                    "",
                )
            ),
        )
        self.release_json = self.root / "release.json"
        self.manifest_json = self.root / "manifest.json"
        self.candidate_compose = self.root / "candidate-compose.yaml"
        self.candidate_apply = self.root / "candidate-apply.sh"
        self.candidate_updater = self.root / "candidate-updater.sh"
        self.apply_log = self.root / "apply.log"
        self.docker_log = self.root / "docker.log"
        self.source_archive = self.root / "source.tar.gz"

        self.write_release(tag="v0.7.0", version="0.7.0", repository="MelodyKnit/SmartAnswer")
        self.write_text(
            self.candidate_compose,
            """services:
  study-qb-assistant:
    image: release-placeholder
# STQB_IMAGE_REF
""",
        )
        self.write_executable(
            self.candidate_apply,
            """#!/usr/bin/env bash
set -euo pipefail
project_dir="$1"
printf '%s' "$*" > "$FAKE_APPLY_LOG"
printf '%s' "$2" > "$FAKE_APPLY_IMAGE"
rm -f "$project_dir/deploy/docker-compose.release.yaml"
""",
        )
        self.write_executable(self.candidate_updater, """#!/usr/bin/env bash
exit 0
""")
        self.write_source_archive()
        self.install_fake_commands()
        self.config_file = self.root / "update.env"
        self.write_config()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_successful_pull_applies_release_and_installs_next_updater(self) -> None:
        """新版本通过 manifest 校验后调用本地应用脚本并更新脚本。"""

        completed = self.run_updater()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(NEW_IMAGE, self.apply_log.read_text(encoding="utf-8"))
        self.assertEqual(
            (self.deploy_dir / "apply-release.sh").read_text(encoding="utf-8"),
            self.candidate_apply.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (self.deploy_dir / "update-from-github.sh").read_text(encoding="utf-8"),
            self.candidate_updater.read_text(encoding="utf-8"),
        )
        self.assertFalse((self.deploy_dir / "docker-compose.release.yaml").exists())

    def test_private_registry_falls_back_to_validated_source(self) -> None:
        """GHCR 不可读时，从相同 Release 提交构建本地镜像后继续部署。"""

        completed = self.run_updater(docker_pull_fails=True)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        apply_log = self.apply_log.read_text(encoding="utf-8")
        self.assertIn("stqb-local/smartanswer:release-0.7.0-aaaaaaaaaaaa", apply_log)
        self.assertIn(NEW_IMAGE, apply_log)
        self.assertIn("building the validated Release source locally", completed.stdout)
        self.assertIn("build --pull", self.docker_log.read_text(encoding="utf-8"))

    def test_source_fallback_can_be_disabled(self) -> None:
        """关闭源码回退后，私有镜像不可读应在切换前失败。"""

        self.write_text(
            self.config_file,
            self.config_file.read_text(encoding="utf-8")
            + "STQB_ALLOW_SOURCE_FALLBACK=false\n",
        )

        completed = self.run_updater(docker_pull_fails=True)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("source fallback is disabled", completed.stderr)
        self.assertFalse(self.apply_log.exists())

    def test_local_fallback_release_is_idempotent(self) -> None:
        """本地构建镜像通过远程 Release digest 识别为同一版本。"""

        local_image = "stqb-local/smartanswer:release-0.7.0-aaaaaaaaaaaa"
        self.write_text(
            self.project_dir / ".env.release",
            chr(10).join(
                (
                    f"STQB_IMAGE_REF={local_image}",
                    f"STQB_RELEASE_IMAGE_REF={NEW_IMAGE}",
                    f"STQB_RELEASE_VERSION={NEW_VERSION}",
                    f"STQB_RELEASE_SHA={NEW_SHA}",
                    "",
                )
            ),
        )

        completed = self.run_updater()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("already running 0.7.0", completed.stdout)
        self.assertFalse(self.apply_log.exists())

    def test_current_release_is_idempotent(self) -> None:
        """同一版本和 digest 重复轮询时不重新拉取或重启容器。"""

        self.write_text(
            self.project_dir / ".env.release",
            chr(10).join(
                (
                    f"STQB_IMAGE_REF={NEW_IMAGE}",
                    f"STQB_RELEASE_VERSION={NEW_VERSION}",
                    f"STQB_RELEASE_SHA={NEW_SHA}",
                    "",
                )
            ),
        )

        completed = self.run_updater()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("already running 0.7.0", completed.stdout)
        self.assertFalse(self.apply_log.exists())

    def test_same_version_with_different_digest_is_rejected(self) -> None:
        """相同版本指向不同 digest 时必须停止，不能静默覆盖不可变发布。"""

        self.write_text(
            self.project_dir / ".env.release",
            chr(10).join(
                (
                    f"STQB_IMAGE_REF={OLD_IMAGE}",
                    f"STQB_RELEASE_VERSION={NEW_VERSION}",
                    f"STQB_RELEASE_SHA={NEW_SHA}",
                    "",
                )
            ),
        )

        completed = self.run_updater()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("same release version points to a different image digest", completed.stderr)
        self.assertFalse(self.apply_log.exists())

    def test_manifest_repository_mismatch_is_rejected_before_apply(self) -> None:
        """来自其他仓库的 manifest 不能被本地服务器执行。"""

        self.write_release(tag="v0.7.0", version="0.7.0", repository="other/repository")

        completed = self.run_updater()

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("release manifest repository does not match local configuration", completed.stderr)
        self.assertFalse(self.apply_log.exists())

    def test_newer_local_version_is_not_downgraded(self) -> None:
        """服务器已有更高版本时，普通轮询不执行降级。"""

        self.write_text(
            self.project_dir / ".env.release",
            chr(10).join(
                (
                    f"STQB_IMAGE_REF={NEW_IMAGE}",
                    "STQB_RELEASE_VERSION=0.8.0",
                    "STQB_RELEASE_SHA=" + "e" * 40,
                    "",
                )
            ),
        )

        completed = self.run_updater()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("skipping downgrade", completed.stdout)
        self.assertFalse(self.apply_log.exists())

    def test_github_api_token_does_not_imply_ghcr_login(self) -> None:
        """GitHub API 令牌和 GHCR 令牌必须独立配置。"""

        github_token_file = self.root / "github-token"
        self.write_text(github_token_file, "github-token-placeholder\n")
        self.config_file.write_text(
            self.config_file.read_text(encoding="utf-8")
            + f"STQB_GITHUB_TOKEN_FILE={self.bash_path(github_token_file)}\n",
            encoding="utf-8",
            newline="",
        )

        completed = self.run_updater()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("login ghcr.io", self.docker_log.read_text(encoding="utf-8"))

    def test_cleanup_only_prunes_old_release_data_and_owned_images(self) -> None:
        """维护模式保留回滚窗口且只清理本项目的快照和镜像。"""

        backup_root = self.project_dir / "deploy-data" / "backups" / "releases"
        for index in range(1, 5):
            backup = backup_root / f"2026100{index}T000000Z-0.19.{index}"
            backup.mkdir(parents=True)
            self.write_text(backup / "study-qb.sqlite3", f"snapshot {index}")
        unrelated = backup_root / "manual-export"
        unrelated.mkdir()
        self.write_text(unrelated / "note.txt", "operator data")

        image_rows = self.root / "docker-images.txt"
        self.write_text(
            image_rows,
            "\n".join(
                (
                    f"ghcr.io/melodyknit/smartanswer <none> sha256:{'1' * 64} sha256:{'a' * 64}",
                    f"ghcr.io/melodyknit/smartanswer <none> sha256:{'2' * 64} sha256:{'b' * 64}",
                    f"ghcr.io/melodyknit/smartanswer <none> sha256:{'3' * 64} sha256:{'c' * 64}",
                    "ghcr.io/another/project <none> sha256:" + "4" * 64 + " sha256:" + "d" * 64,
                    "stqb-local/smartanswer release-0.19.2-cccccccccccc <none> sha256:" + "e" * 64,
                    "stqb-local/smartanswer release-0.19.1-bbbbbbbbbbbb <none> sha256:" + "f" * 64,
                    "stqb-local/smartanswer release-0.19.0-aaaaaaaaaaaa <none> sha256:" + "0" * 64,
                    "",
                )
            ),
        )
        removed_images = self.root / "removed-images.txt"
        curl_log = self.root / "curl.log"

        completed = self.run_updater(
            cleanup_only=True,
            image_rows=image_rows,
            removed_images=removed_images,
            active_image_id="sha256:" + "a" * 64,
            curl_log=curl_log,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        retained = sorted(
            path.name
            for path in backup_root.iterdir()
            if path.is_dir() and path.name.startswith("202610")
        )
        self.assertEqual(
            retained,
            ["20261003T000000Z-0.19.3", "20261004T000000Z-0.19.4"],
        )
        self.assertTrue((unrelated / "note.txt").is_file())
        removed = removed_images.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"ghcr.io/melodyknit/smartanswer@sha256:{'3' * 64}", removed)
        self.assertIn("stqb-local/smartanswer:release-0.19.0-aaaaaaaaaaaa", removed)
        self.assertFalse(any("another/project" in item for item in removed))
        self.assertFalse(curl_log.exists())
        self.assertFalse(self.apply_log.exists())

    def test_cleanup_refuses_zero_backup_retention_before_deleting(self) -> None:
        """保留数为零时更新器应拒绝运行，且不改动快照目录。"""

        backup_root = self.project_dir / "deploy-data" / "backups" / "releases"
        backup = backup_root / "20261001T000000Z-0.19.0"
        backup.mkdir(parents=True)
        self.write_text(backup / "study-qb.sqlite3", "snapshot")
        with self.config_file.open("a", encoding="utf-8") as handle:
            handle.write("STQB_RELEASE_BACKUP_KEEP=0\n")

        completed = self.run_updater(cleanup_only=True)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("STQB_RELEASE_BACKUP_KEEP must be between 1 and 100", completed.stderr)
        self.assertTrue((backup / "study-qb.sqlite3").is_file())

    def test_cleanup_preview_reports_candidates_without_removing_storage(self) -> None:
        """预览与执行共用策略，但预览不能改变快照或镜像。"""

        root = self.project_dir / "deploy-data/backups/releases"
        for index in range(1, 4):
            directory = root / f"2026100{index}T000000Z-0.19.{index}"
            directory.mkdir(parents=True)
            self.write_text(directory / "study-qb.sqlite3", "snapshot")
        completed = self.run_updater(cleanup_preview=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("would remove release snapshot: 20261001", completed.stdout)
        self.assertEqual(len(list(root.iterdir())), 3)
        self.assertNotIn("image rm", self.docker_log.read_text(encoding="utf-8"))

    @unittest.skipIf(os.name == "nt", "Windows hosts may not permit directory symlinks")
    def test_symlinked_backup_parent_is_rejected_without_removing_external_data(self) -> None:
        """备份父目录被链接到其他路径时必须拒绝清理。"""

        outside = self.root / "operator-data"
        for index in range(1, 4):
            directory = outside / f"releases/2026100{index}T000000Z-0.19.{index}"
            directory.mkdir(parents=True)
            self.write_text(directory / "study-qb.sqlite3", "private data")
        data_root = self.project_dir / "deploy-data"
        data_root.mkdir()
        (data_root / "backups").symlink_to(outside, target_is_directory=True)
        completed = self.run_updater(cleanup_only=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("symlink", completed.stdout)
        self.assertEqual(len(list((outside / "releases").iterdir())), 3)

    def test_regular_update_cleans_before_pulling_candidate_image(self) -> None:
        """新旧镜像和旧数据库快照先清理，再拉取候选镜像。"""

        backup_root = self.project_dir / "deploy-data" / "backups" / "releases"
        old_backups = []
        for index in range(1, 5):
            backup = backup_root / f"2026100{index}T000000Z-0.19.{index}"
            backup.mkdir(parents=True)
            self.write_text(backup / "study-qb.sqlite3", "old rollback")
            old_backups.append(backup)
        image_rows = self.root / "docker-images.txt"
        self.write_text(
            image_rows,
            "\n".join(
                (
                    f"ghcr.io/melodyknit/smartanswer <none> sha256:{'a' * 64} sha256:{'1' * 64}",
                    f"ghcr.io/melodyknit/smartanswer <none> sha256:{'b' * 64} sha256:{'2' * 64}",
                    f"ghcr.io/melodyknit/smartanswer <none> sha256:{'c' * 64} sha256:{'3' * 64}",
                    "",
                )
            ),
        )
        removed_images = self.root / "removed-images.txt"

        completed = self.run_updater(
            image_rows=image_rows,
            removed_images=removed_images,
            active_image_id="sha256:" + "1" * 64,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        retained_backups = sorted(
            path.name
            for path in backup_root.iterdir()
            if path.is_dir() and path.name.startswith("202610")
        )
        self.assertEqual(retained_backups, ["20261003T000000Z-0.19.3", "20261004T000000Z-0.19.4"])
        docker_events = self.docker_log.read_text(encoding="utf-8").splitlines()
        cleanup_position = next(i for i, line in enumerate(docker_events) if "image rm" in line)
        pull_position = next(i for i, line in enumerate(docker_events) if line.startswith("pull "))
        self.assertLess(cleanup_position, pull_position)
        self.assertIn(f"ghcr.io/melodyknit/smartanswer@sha256:{'c' * 64}", removed_images.read_text(encoding="utf-8"))

    def test_cleanup_keeps_all_container_images_and_removes_version_aliases(self) -> None:
        """历史镜像的版本标签也要回收，其他容器或其他仓库引用的镜像不能删除。"""

        image_rows = self.root / "docker-images.txt"
        self.write_text(
            image_rows,
            "\n".join([
                f"ghcr.io/melodyknit/smartanswer 0.20.0 sha256:{'1' * 64} sha256:{'a' * 64}",
                f"ghcr.io/melodyknit/smartanswer 0.19.2 sha256:{'2' * 64} sha256:{'b' * 64}",
                f"ghcr.io/melodyknit/smartanswer 0.19.0 sha256:{'3' * 64} sha256:{'c' * 64}",
                f"ghcr.io/melodyknit/smartanswer v0.19.0 sha256:{'3' * 64} sha256:{'c' * 64}",
                f"ghcr.io/melodyknit/smartanswer 0.18.0 sha256:{'4' * 64} sha256:{'d' * 64}",
                f"ghcr.io/another/project saved <none> sha256:{'d' * 64}",
                f"ghcr.io/melodyknit/smartanswer 0.17.0 sha256:{'5' * 64} sha256:{'e' * 64}",
            ]) + "\n",
        )
        removed_images = self.root / "removed-images.txt"
        completed = self.run_updater(
            cleanup_only=True, image_rows=image_rows, removed_images=removed_images,
            active_image_id="sha256:" + "a" * 64,
            used_image_ids=["sha256:" + "a" * 64, "sha256:" + "e" * 64],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        # Three owned images remain: two used by containers, plus one rollback.
        removed = removed_images.read_text(encoding="utf-8")
        self.assertIn("ghcr.io/melodyknit/smartanswer:0.19.0", removed)
        self.assertIn("ghcr.io/melodyknit/smartanswer:v0.19.0", removed)
        self.assertNotIn("ghcr.io/melodyknit/smartanswer:0.17.0", removed)
        self.assertNotIn("ghcr.io/melodyknit/smartanswer:0.18.0", removed)

    def test_cleanup_incomplete_snapshot_does_not_displace_valid_rollback(self) -> None:
        """新但未完成的备份不能占用保留名额，也不能被自动删除。"""

        backup_root = self.project_dir / "deploy-data" / "backups" / "releases"
        for index in range(1, 4):
            backup = backup_root / f"2026100{index}T000000Z-v0.19.{index}-manual"
            backup.mkdir(parents=True)
            self.write_text(backup / "study-qb.sqlite3", "snapshot")
        partial = backup_root / "20261004T000000Z-0.20.0"
        partial.mkdir()
        self.write_text(partial / "study-qb.sqlite3", "unfinished")
        self.write_text(partial / ".incomplete", "")
        completed = self.run_updater(cleanup_only=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse((backup_root / "20261001T000000Z-v0.19.1-manual").exists())
        self.assertTrue((backup_root / "20261002T000000Z-v0.19.2-manual").is_dir())
        self.assertTrue(partial.is_dir())

    def test_updater_has_no_github_ssh_deployment_binding(self) -> None:
        """更新器和发布工作流不应重新引入中心 SSH 部署绑定。"""

        updater = UPDATER_SCRIPT.read_text(encoding="utf-8")
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("STQB_SOURCE_REPOSITORY", updater)
        self.assertIn("release-manifest.json", updater)
        self.assertNotIn("DEPLOY_HOST", updater)
        self.assertNotIn("DEPLOY_SSH_PRIVATE_KEY", updater)
        self.assertNotIn("production", workflow)
        self.assertNotIn("DEPLOY_HOST", workflow)
        self.assertNotIn("ssh ", workflow)

    def write_release(self, *, tag: str, version: str, repository: str) -> None:
        """写入可控的 Release API 和 manifest 响应。"""

        release_payload = {
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "release-manifest.json",
                    "url": "https://api.github.com/repos/MelodyKnit/SmartAnswer/releases/assets/1",
                }
            ],
        }
        manifest_payload = {
            "schema_version": 1,
            "version": version,
            "tag": tag,
            "repository": repository,
            "commit_sha": NEW_SHA,
            "image": "ghcr.io/melodyknit/smartanswer",
            "image_digest": f"sha256:{NEW_DIGEST}",
            "platform": "linux/amd64",
        }
        self.write_text(self.release_json, json.dumps(release_payload))
        self.write_text(self.manifest_json, json.dumps(manifest_payload))

    def write_config(self) -> None:
        """写入不含凭据的服务器本地配置。"""

        self.write_text(
            self.config_file,
            chr(10).join(
                (
                    f"STQB_PROJECT_DIR={self.bash_path(self.project_dir)}",
                    "STQB_SOURCE_REPOSITORY=MelodyKnit/SmartAnswer",
                    "STQB_HEALTH_URL=http://127.0.0.1:3003",
                    "STQB_DOCKER_CONTEXT=rootless",
                    "STQB_PLATFORM=linux/amd64",
                    "STQB_ALLOW_DOWNGRADE=false",
                    "STQB_RELEASE_BACKUP_KEEP=2",
                    "STQB_RELEASE_IMAGE_KEEP=2",
                    "",
                )
            ),
        )

    def run_updater(
        self,
        *,
        docker_pull_fails: bool = False,
        cleanup_only: bool = False,
        cleanup_preview: bool = False,
        image_rows: Path | None = None,
        removed_images: Path | None = None,
        active_image_id: str = "",
        curl_log: Path | None = None,
        used_image_ids: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """使用伪造 GitHub、Docker 和 flock 命令执行完整拉取流程。"""

        environment = {
            **os.environ,
            "FAKE_BIN": self.bash_path(self.fake_bin),
            "FAKE_RELEASE_JSON": self.bash_path(self.release_json),
            "FAKE_MANIFEST_JSON": self.bash_path(self.manifest_json),
            "FAKE_COMPOSE": self.bash_path(self.candidate_compose),
            "FAKE_APPLY": self.bash_path(self.candidate_apply),
            "FAKE_UPDATER": self.bash_path(self.candidate_updater),
            "FAKE_APPLY_LOG": self.bash_path(self.apply_log),
            "FAKE_APPLY_IMAGE": self.bash_path(self.root / "apply-image.txt"),
            "FAKE_DOCKER_LOG": self.bash_path(self.docker_log),
            "FAKE_SOURCE_ARCHIVE": self.bash_path(self.source_archive),
            "FAKE_PYTHON": self.bash_path(Path(sys.executable)),
            "FAKE_VERSION": NEW_VERSION,
            "FAKE_SHA": NEW_SHA,
            "FAKE_DOCKER_PULL_FAILS": "1" if docker_pull_fails else "0",
            "FAKE_DOCKER_IMAGES": self.bash_path(image_rows) if image_rows else "",
            "FAKE_DOCKER_REMOVED_IMAGES": self.bash_path(removed_images) if removed_images else "",
            "FAKE_ACTIVE_IMAGE_ID": active_image_id,
            "FAKE_CURL_LOG": self.bash_path(curl_log) if curl_log else "",
            "FAKE_USED_IMAGE_IDS": "\n".join(used_image_ids or []),
        }
        updater_args = [self.bash_path(UPDATER_SCRIPT)]
        if cleanup_preview:
            updater_args.append("--cleanup-preview")
        elif cleanup_only:
            updater_args.append("--cleanup-only")
        updater_args.append(self.bash_path(self.config_file))
        command = [
            str(self.bash),
            "-c",
            'export PATH="$FAKE_BIN:/usr/bin:/bin"; exec bash "$@"',
            "updater-test",
            *updater_args,
        ]
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            env=environment,
            timeout=30,
        )

    def install_fake_commands(self) -> None:
        """安装不会访问真实网络或 Docker 的测试命令。"""

        curl_script = r'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_CURL_LOG:-/dev/null}"
args="$*"
case "$args" in
  *"/releases/latest"*|*"/releases/tags/"*) cat "$FAKE_RELEASE_JSON" ;;
  *"/releases/assets/"*) cat "$FAKE_MANIFEST_JSON" ;;
  *"/tarball/"*) cat "$FAKE_SOURCE_ARCHIVE" ;;
  *"/contents/docker-compose.yaml"*) cat "$FAKE_COMPOSE" ;;
  *"/contents/deploy/apply-release.sh"*) cat "$FAKE_APPLY" ;;
  *"/contents/deploy/update-from-github.sh"*) cat "$FAKE_UPDATER" ;;
  *) echo "unexpected URL" >&2; exit 1 ;;
esac
'''
        docker_script = r'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
if [[ "$#" -ge 2 && "$1" == "context" && "$2" == "show" ]]; then
  printf 'rootless'
elif [[ "${1:-}" == "container" && "${2:-}" == "ls" ]]; then
  if [[ -n "${FAKE_USED_IMAGE_IDS:-}" ]]; then printf 'other-container\n'; fi
elif [[ "${1:-}" == "inspect" && " $* " == *".Image"* ]]; then
  if [[ "${!#}" == "study-qb-assistant" ]]; then
    printf '%s\n' "${FAKE_ACTIVE_IMAGE_ID:-}"
  else
    printf '%s\n' "${FAKE_USED_IMAGE_IDS:-}"
  fi
elif [[ "${1:-}" == "image" && "${2:-}" == "ls" ]]; then
  if [[ -n "${FAKE_DOCKER_IMAGES:-}" && -f "$FAKE_DOCKER_IMAGES" ]]; then
    cat "$FAKE_DOCKER_IMAGES"
  fi
elif [[ "${1:-}" == "image" && "${2:-}" == "inspect" && " $* " == *".Config.Labels"* ]]; then
  printf 'https://github.com/MelodyKnit/SmartAnswer\n'
elif [[ "${1:-}" == "image" && "${2:-}" == "rm" ]]; then
  printf '%s\n' "${@:3}" >> "$FAKE_DOCKER_REMOVED_IMAGES"
elif [[ "${1:-}" == "pull" && "${FAKE_DOCKER_PULL_FAILS:-0}" == "1" ]]; then
  exit 1
elif [[ "${1:-}" == "build" ]]; then
  exit 0
elif [[ "${1:-}" == "run" ]]; then
  printf '%s:%s\n' "$FAKE_VERSION" "$FAKE_SHA"
elif [[ "$#" -ge 1 && "$1" == "login" ]]; then
  cat >/dev/null
fi
'''
        flock_script = """#!/usr/bin/env bash
exit 0
"""
        python_script = """#!/usr/bin/env bash
exec "$FAKE_PYTHON" "$@"
"""
        self.write_executable(self.fake_bin / "curl", curl_script)
        self.write_executable(self.fake_bin / "docker", docker_script)
        self.write_executable(self.fake_bin / "flock", flock_script)
        self.write_executable(self.fake_bin / "python3", python_script)

    def write_source_archive(self) -> None:
        """写入 GitHub tarball 形态的最小源码归档。"""

        files = {
            "smartanswer-bda0698/Dockerfile": b"FROM scratch\n",
            "smartanswer-bda0698/docker-compose.yaml": b"services:\n",
        }
        with tarfile.open(self.source_archive, mode="w:gz") as archive:
            for name, content in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, fileobj=io.BytesIO(content))

    def bash_path(self, path: Path) -> str:
        """把 Windows 原生路径转换成 Git Bash 可读取的路径。"""

        if os.name != "nt":
            return str(path)
        completed = subprocess.run(
            [str(self.bash), "-lc", 'cygpath -u -- "$1"', "bash", str(path)],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
        return completed.stdout.strip()

    @staticmethod
    def write_text(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8", newline="")

    @classmethod
    def write_executable(cls, path: Path, content: str) -> None:
        cls.write_text(path, content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
