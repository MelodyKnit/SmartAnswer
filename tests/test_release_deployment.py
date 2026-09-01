"""服务器本地发布切换脚本回归测试。"""

from __future__ import annotations

import os
import signal
import shutil
import stat
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = PROJECT_ROOT / "deploy" / "apply-release.sh"
RELEASE_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
    OLD_VERSION = str(tomllib.load(project_file)["project"]["version"])
major, minor, patch = (int(part) for part in OLD_VERSION.split("."))
NEW_VERSION = f"{major}.{minor}.{patch + 1}"
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


class ApplyReleaseScriptTests(unittest.TestCase):
    """验证本地发布切换脚本的成功切换和自动回滚。"""

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
        self.deploy_dir.mkdir(parents=True)
        self.fake_bin.mkdir()
        self.write_text(self.project_dir / "docker-compose.yaml", "services:\n  old-release: {}\n")
        self.write_text(
            self.deploy_dir / "docker-compose.release.yaml",
            "services:\n  new-release: {}\n",
        )
        self.write_text(
            self.project_dir / "docker-compose.override.yml",
            "services:\n  study-qb-assistant:\n    image: local-operator-image:old\n",
        )
        self.write_text(
            self.project_dir / ".env.release",
            "\n".join(
                (
                    f"STQB_IMAGE_REF={OLD_IMAGE}",
                    f"STQB_RELEASE_VERSION={OLD_VERSION}",
                    "STQB_RELEASE_SHA=" + "d" * 40,
                    "",
                )
            ),
        )
        self.docker_log = self.root / "docker.log"
        self.up_counter = self.root / "compose-up-count"
        self.install_fake_commands()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_successful_release_switches_compose_and_image_digest(self) -> None:
        """候选镜像通过预检和健康检查后才替换当前发布。"""

        completed = self.run_release(health_version=NEW_VERSION)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("new-release", (self.project_dir / "docker-compose.yaml").read_text(encoding="utf-8"))
        release_environment = (self.project_dir / ".env.release").read_text(encoding="utf-8")
        self.assertIn(f"STQB_IMAGE_REF={NEW_IMAGE}", release_environment)
        self.assertIn(f"STQB_RELEASE_VERSION={NEW_VERSION}", release_environment)
        self.assertFalse((self.deploy_dir / "docker-compose.release.yaml").exists())
        image_override = self.deploy_dir / "docker-compose.release-image.yaml"
        self.assertTrue(image_override.exists())
        self.assertIn("image: ${STQB_IMAGE_REF", image_override.read_text(encoding="utf-8"))
        docker_commands = self.docker_log.read_text(encoding="utf-8")
        self.assertIn(f"pull {NEW_IMAGE}", docker_commands)
        self.assertIn(
            self.bash_path(self.project_dir / "docker-compose.override.yml"),
            docker_commands,
        )
        self.assertIn(self.bash_path(image_override), docker_commands)
        self.assertLess(
            docker_commands.index(self.bash_path(self.project_dir / "docker-compose.override.yml")),
            docker_commands.index(self.bash_path(image_override)),
        )
        self.assertNotIn("login", docker_commands)

    def test_compose_failure_restores_previous_release(self) -> None:
        """新容器首次启动失败时恢复旧 Compose 与旧镜像引用。"""

        completed = self.run_release(health_version=OLD_VERSION, fail_first_up=True)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("previous release was restored", completed.stderr)
        self.assertIn("old-release", (self.project_dir / "docker-compose.yaml").read_text(encoding="utf-8"))
        release_environment = (self.project_dir / ".env.release").read_text(encoding="utf-8")
        self.assertIn(f"STQB_IMAGE_REF={OLD_IMAGE}", release_environment)
        self.assertIn(f"STQB_RELEASE_VERSION={OLD_VERSION}", release_environment)
        self.assertEqual(self.up_counter.read_text(encoding="utf-8").strip(), "2")

    def test_running_container_uses_configured_sqlite_path_for_backup(self) -> None:
        """自定义 SQLite 路径必须通过容器配置解析，并保存到发布快照目录。"""

        database_path = self.project_dir / "deploy-data" / "runtime" / "custom.sqlite3"
        database_path.parent.mkdir(parents=True)
        self.write_text(database_path, "database snapshot source")

        completed = self.run_release(
            health_version=NEW_VERSION,
            running_database_path="/app/data/runtime/custom.sqlite3",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        backups = list((self.project_dir / "deploy-data" / "backups" / "releases").rglob("custom.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "database snapshot source")

    def test_external_database_skips_sqlite_snapshot_without_failing(self) -> None:
        """外部数据库不应因 SQLite 文件不存在而阻断镜像发布。"""

        completed = self.run_release(
            health_version=NEW_VERSION,
            running_database_path="external",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse((self.project_dir / "deploy-data" / "backups").exists())

    def test_release_workflow_triggers_for_version_tags(self) -> None:
        """正式版本标签必须触发校验和 Release 发布，不包含服务器部署绑定。"""

        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("push:", workflow)
        self.assertIn('"v*"', workflow)
        self.assertIn("SOURCE_REPOSITORY=${{ github.repository }}", workflow)
        self.assertNotIn("GHCR_READ_TOKEN", workflow)
        self.assertNotIn("DEPLOY_HOST", workflow)
        self.assertNotIn("DEPLOY_SSH_PRIVATE_KEY", workflow)
        self.assertNotIn("production", workflow)

    def test_release_workflow_pins_ruff_version(self) -> None:
        """发布校验必须使用确定的 Ruff 版本，避免默认规则随上游变动。"""

        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("ruff==0.15.21", workflow)
        self.assertIn("ruff --version", workflow)

    def test_release_workflow_retries_transient_npm_install_failures(self) -> None:
        """前端依赖下载遇到瞬时网络重置时应重试，再进入构建阶段。"""

        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Install frontend dependencies", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("npm ci --prefer-offline --no-audit --fund=false", workflow)
        self.assertIn('npm_config_fetch_retries: "5"', workflow)
        self.assertLess(
            workflow.index("Install frontend dependencies"),
            workflow.index("Build frontend"),
        )

    def test_release_script_resolves_the_running_sqlite_database_path(self) -> None:
        """发布备份必须遵从容器实际数据库配置，而非假设固定文件名。"""

        script = RELEASE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("from study_qb_assistant.config import get_global_config", script)
        self.assertIn("config.database_path_resolved", script)
        self.assertIn('SQLite database is outside the data mount', script)
        self.assertIn('source = sqlite3.connect(sys.argv[1])', script)
        self.assertIn("docker context show", script)
        self.assertIn("docker-compose.release-image.yaml", script)
        self.assertIn("capture_unmanaged_release", script)

    def test_first_release_failure_restores_original_files(self) -> None:
        """首次发布无法启动时不应在服务器留下候选发布配置。"""

        (self.project_dir / ".env.release").unlink()

        completed = self.run_release(health_version=OLD_VERSION, fail_first_up=True)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("No prior release is available", completed.stderr)
        self.assertIn("old-release", (self.project_dir / "docker-compose.yaml").read_text(encoding="utf-8"))
        self.assertFalse((self.project_dir / ".env.release").exists())
        self.assertFalse((self.deploy_dir / "docker-compose.release.yaml").exists())
        self.assertFalse((self.deploy_dir / "docker-compose.release-image.yaml").exists())

    def test_unmanaged_running_container_is_restored_without_leaving_release_files(self) -> None:
        """首次纳管失败时，原有 rootless 容器仍可作为回滚目标。"""

        (self.project_dir / ".env.release").unlink()

        completed = self.run_release(
            health_version=OLD_VERSION,
            fail_first_up=True,
            running_database_path="external",
            running_image=OLD_IMAGE,
            running_version=OLD_VERSION,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("previous release was restored", completed.stderr)
        self.assertIn("old-release", (self.project_dir / "docker-compose.yaml").read_text(encoding="utf-8"))
        self.assertFalse((self.project_dir / ".env.release").exists())
        self.assertFalse((self.deploy_dir / "docker-compose.release-image.yaml").exists())
        self.assertEqual(self.up_counter.read_text(encoding="utf-8").strip(), "2")

    def test_release_refuses_to_use_an_unexpected_docker_context(self) -> None:
        """上下文不匹配时必须在拉取镜像或写入文件前失败。"""

        completed = self.run_release(
            health_version=NEW_VERSION,
            docker_context="default",
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Docker context must be rootless", completed.stderr)
        self.assertEqual(self.docker_log.read_text(encoding="utf-8"), "context show\n")

    def run_release(
        self,
        *,
        health_version: str,
        fail_first_up: bool = False,
        running_database_path: str = "",
        running_image: str = "",
        running_version: str = "",
        docker_context: str = "rootless",
    ) -> subprocess.CompletedProcess[str]:
        """通过伪造外部命令执行完整发布流程。"""

        environment = {
            **os.environ,
            "FAKE_BIN": self.bash_path(self.fake_bin),
            "FAKE_VERSION": NEW_VERSION,
            "FAKE_SHA": NEW_SHA,
            "FAKE_HEALTH_VERSION": health_version,
            "FAKE_DOCKER_LOG": self.bash_path(self.docker_log),
            "FAKE_UP_COUNTER": self.bash_path(self.up_counter),
            "FAKE_FAIL_FIRST_UP": "1" if fail_first_up else "0",
            "FAKE_PROJECT_DIR": self.bash_path(self.project_dir),
            "FAKE_RUNNING_DATABASE_PATH": running_database_path,
            "FAKE_RUNNING_IMAGE": running_image,
            "FAKE_RUNNING_VERSION": running_version,
            "FAKE_RUNNING_SHA": "c" * 40,
            "FAKE_DOCKER_CONTEXT": docker_context,
        }
        command = [
            str(self.bash),
            "-c",
            'export PATH="$FAKE_BIN:/usr/bin:/bin"; exec bash "$@"',
            "release-test",
            self.bash_path(RELEASE_SCRIPT),
            self.bash_path(self.project_dir),
            NEW_IMAGE,
            NEW_VERSION,
            NEW_SHA,
            "http://127.0.0.1:3003",
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
            env=environment,
            start_new_session=os.name != "nt",
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            self.terminate_process_tree(process)
            stdout, stderr = process.communicate()
            self.fail(
                "发布脚本测试超时，已终止隔离进程树。\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout,
            stderr,
        )

    @staticmethod
    def terminate_process_tree(process: subprocess.Popen[str]) -> None:
        """测试超时时终止子进程树，防止遗留外部命令。"""

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
            return
        os.killpg(process.pid, signal.SIGKILL)

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

    def install_fake_commands(self) -> None:
        """安装不会接触真实 Docker、网络和服务器数据的测试命令。"""

        docker_script = r'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
command="${1:-}"
case "$command" in
  inspect)
    if [[ " $* " == *".State.Running"* ]] && [[ -n "${FAKE_RUNNING_DATABASE_PATH:-}${FAKE_RUNNING_IMAGE:-}" ]]; then
      printf 'true\n'
    elif [[ " $* " == *".Config.Image"* ]] && [[ -n "${FAKE_RUNNING_IMAGE:-}" ]]; then
      printf '%s\n' "$FAKE_RUNNING_IMAGE"
    fi
    ;;
  exec)
    shift
    service_name="${1:-}"
    shift || true
    if [[ "$service_name" != "study-qb-assistant" ]]; then
      exit 1
    fi
    if [[ "${1:-}" == "python" && " $* " == *BUILD_INFO* ]]; then
      printf '%s:%s\n' "$FAKE_RUNNING_VERSION" "$FAKE_RUNNING_SHA"
    elif [[ "${1:-}" == "python" && " $* " == *get_global_config* ]]; then
      printf '%s\n' "$FAKE_RUNNING_DATABASE_PATH"
    elif [[ "${1:-}" == "mkdir" ]]; then
      container_path="${!#}"
      mkdir -p "$FAKE_PROJECT_DIR/deploy-data${container_path#/app/data}"
    elif [[ "${1:-}" == "python" ]]; then
      source_path="${@: -2:1}"
      target_path="${!#}"
      source_path="$FAKE_PROJECT_DIR/deploy-data${source_path#/app/data}"
      target_path="$FAKE_PROJECT_DIR/deploy-data${target_path#/app/data}"
      mkdir -p "$(dirname "$target_path")"
      cp "$source_path" "$target_path"
    fi
    ;;
  run)
    printf '%s:%s\n' "$FAKE_VERSION" "$FAKE_SHA"
    ;;
  compose)
    shift
    if [[ " $* " == *" up -d --no-build study-qb-assistant "* ]]; then
      count=0
      if [[ -f "$FAKE_UP_COUNTER" ]]; then
        count="$(cat "$FAKE_UP_COUNTER")"
      fi
      count=$((count + 1))
      printf '%s\n' "$count" > "$FAKE_UP_COUNTER"
      if [[ "$FAKE_FAIL_FIRST_UP" == "1" && "$count" == "1" ]]; then
        exit 1
      fi
    fi
    ;;
  context)
    if [[ "${2:-}" == "show" ]]; then
      printf '%s\n' "$FAKE_DOCKER_CONTEXT"
    fi
    ;;
esac
'''
        curl_script = r'''#!/usr/bin/env bash
set -euo pipefail
url="${!#}"
if [[ "$url" == */healthz ]]; then
  printf '{"ok":true}\n'
else
  printf '{"ok":true,"version":"%s"}\n' "$FAKE_HEALTH_VERSION"
fi
'''
        self.write_executable(self.fake_bin / "docker", docker_script)
        self.write_executable(self.fake_bin / "curl", curl_script)

    @staticmethod
    def write_text(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8", newline="\n")

    @classmethod
    def write_executable(cls, path: Path, content: str) -> None:
        cls.write_text(path, content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
