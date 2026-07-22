"""GitHub Actions 远程发布脚本回归测试。"""

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
RELEASE_SCRIPT = PROJECT_ROOT / "deploy" / "remote-release.sh"
RELEASE_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
UPDATE_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "deploy-release.yml"
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


class RemoteReleaseScriptTests(unittest.TestCase):
    """验证发布脚本的成功切换和自动回滚。"""

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
        self.assertNotIn("test-read-token", self.docker_log.read_text(encoding="utf-8"))

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

    def test_deployment_workflow_uses_scp_port_option(self) -> None:
        """SCP 必须使用大写 -P，避免非 22 端口被误当成源文件。"""

        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('scp_args=(-P "$DEPLOY_PORT"', workflow)
        self.assertIn('scp "${scp_args[@]}" docker-compose.yaml', workflow)
        self.assertNotIn('scp "${ssh_args[@]}"', workflow)

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

    def test_existing_release_workflow_validates_manifest_before_remote_deploy(self) -> None:
        """项目内更新只能调度已发布且经过 manifest 校验的不可变镜像。"""

        workflow = UPDATE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("release-manifest.json", workflow)
        self.assertIn("Release manifest validation failed", workflow)
        self.assertIn('scp_args=(-P "$DEPLOY_PORT"', workflow)
        self.assertIn("remote-release.sh", workflow)

    def test_first_release_failure_restores_original_files(self) -> None:
        """首次发布无法启动时不应在服务器留下候选发布配置。"""

        (self.project_dir / ".env.release").unlink()

        completed = self.run_release(health_version=OLD_VERSION, fail_first_up=True)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("no prior release is available", completed.stderr)
        self.assertIn("old-release", (self.project_dir / "docker-compose.yaml").read_text(encoding="utf-8"))
        self.assertFalse((self.project_dir / ".env.release").exists())
        self.assertFalse((self.deploy_dir / "docker-compose.release.yaml").exists())

    def run_release(self, *, health_version: str, fail_first_up: bool = False) -> subprocess.CompletedProcess[str]:
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
            "MelodyKnit",
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
            stdout, stderr = process.communicate("test-read-token\n", timeout=20)
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
if [[ "${1:-}" == "--config" ]]; then
  shift 2
fi
command="${1:-}"
case "$command" in
  login)
    cat >/dev/null
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
