"""后端目录边界与版本化 API 的架构回归测试。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "study_qb_assistant"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.questions.models import (  # noqa: E402
    CanonicalQuestionRecord,
)
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


FORBIDDEN_MODULES = (
    "models.py",
    "normalization.py",
    "option_labels.py",
    "question_types.py",
    "query_parsing.py",
    "answer_reuse.py",
    "image_ocr.py",
    "input_anomalies.py",
    "runtime.py",
)

FORBIDDEN_PATHS = (
    "answer_quality",
    "api/routes",
    "api/schemas.py",
    "api/context.py",
    "api/route_support.py",
    "platform/service.py",
    "platform/records.py",
    "storage/platform_repository.py",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "study_qb_assistant.models",
    "study_qb_assistant.normalization",
    "study_qb_assistant.option_labels",
    "study_qb_assistant.question_types",
    "study_qb_assistant.query_parsing",
    "study_qb_assistant.answer_quality",
    "study_qb_assistant.answer_reuse",
    "study_qb_assistant.image_ocr",
    "study_qb_assistant.input_anomalies",
    "study_qb_assistant.runtime",
    "study_qb_assistant.api.routes",
    "study_qb_assistant.api.schemas",
    "study_qb_assistant.platform.service",
    "study_qb_assistant.platform.records",
    "study_qb_assistant.storage.platform_repository",
)


def sample_index() -> LocalQuestionIndex:
    """构造不依赖外部文件的最小题库索引。"""

    return LocalQuestionIndex(
        (
            CanonicalQuestionRecord(
                question_id="architecture:sample",
                title_raw="架构测试题",
                question_type="single",
                options_raw=("A. 正确", "B. 错误"),
                answer_raw="A",
                explanation="用于验证 API 路由边界。",
                subject="test",
                chapter=None,
                tags=("architecture",),
                source_name="architecture-test",
                source_url="",
                source_license="test-only",
                source_split="active",
                source_record_path="",
            ),
        )
    )


def imported_modules(path: Path) -> set[str]:
    """读取 Python 文件中的绝对导入目标。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_removed_internal_modules_do_not_return() -> None:
    """禁止已迁移的顶层模块和巨石模块重新出现。"""

    for name in FORBIDDEN_MODULES:
        assert not (PACKAGE_ROOT / name).exists(), name
    for relative_path in FORBIDDEN_PATHS:
        assert not (PACKAGE_ROOT / relative_path).exists(), relative_path


def test_source_does_not_import_removed_modules() -> None:
    """仓库内源码不得继续依赖已删除的 Python 导入路径。"""

    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        for module in imported_modules(path):
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {module}")
    assert not violations, "\n".join(violations)


def test_api_v1_contains_real_domain_routers() -> None:
    """v1 目录必须包含真实领域路由，而不是只保留转发入口。"""

    router_paths = sorted((PACKAGE_ROOT / "api" / "v1").glob("*/router.py"))
    assert len(router_paths) >= 10
    assert all(path.stat().st_size > 100 for path in router_paths)
    assert (PACKAGE_ROOT / "api" / "static" / "router.py").is_file()


def test_openapi_exposes_only_versioned_business_routes() -> None:
    """规范文档只暴露 v1 业务路径，旧路径仅保留隐藏兼容。"""

    client = TestClient(create_app(sample_index(), require_auth=False))
    openapi_paths = client.get("/api/v1/openapi.json").json()["paths"]

    assert openapi_paths
    assert all(
        path == "/ocs/query" or path.startswith("/api/v1/")
        for path in openapi_paths
    )

    legacy = client.get("/healthz")
    assert legacy.status_code == 200
    assert legacy.headers["Deprecation"] == "true"
    assert "/api/v1/healthz" in legacy.headers["Link"]
