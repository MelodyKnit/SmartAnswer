"""服务器本地 GitHub Release 拉取器回归测试。"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
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
                    "",
                )
            ),
        )

    def run_updater(self) -> subprocess.CompletedProcess[str]:
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
            "FAKE_PYTHON": self.bash_path(Path(sys.executable)),
        }
        command = [
            str(self.bash),
            "-c",
            'export PATH="$FAKE_BIN:/usr/bin:/bin"; exec bash "$@"',
            "updater-test",
            self.bash_path(UPDATER_SCRIPT),
            self.bash_path(self.config_file),
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
args="$*"
case "$args" in
  *"/releases/latest"*|*"/releases/tags/"*) cat "$FAKE_RELEASE_JSON" ;;
  *"/releases/assets/"*) cat "$FAKE_MANIFEST_JSON" ;;
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
