"""运行时启动与服务组装入口。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .answering import AnswerService
from .api.app import create_app
from .auth import AuthService
from .config import get_global_config
from .llm.cache import LlmAnswerCache
from .llm.management import LlmManagementService
from .llm.orchestration import SearchAugmentedModelProvider
from .llm.providers import MultiModelProvider, OpenAICompatibleProvider
from .llm.tools import LocalRagTool, WebSearchTool
from .llm.tools.web_search import build_search_provider
from .llm.tracing import set_trace_sink
from .platform.container import PlatformServices
from .platform.image_generation.worker import ImageGenerationWorker
from .platform.settings import SettingsService
from .logger import configure_external_loggers, log_event
from .search import LocalQuestionIndex

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_env(path: Path | None = None) -> None:
    """加载 `.env` 与 `.env.local`，且不覆盖进程里已有的环境变量。"""

    paths = (path,) if path is not None else (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local")
    for env_path in paths:
        if env_path is None or not env_path.exists():
            continue
        try:
            from dotenv import load_dotenv
        except ImportError:
            load_local_env_fallback(env_path)
            continue
        load_dotenv(env_path, override=False)


def build_runtime_app() -> FastAPI:
    """根据当前运行环境组装 FastAPI 应用。"""

    load_local_env()
    config = get_global_config()
    database_locator = config.database_locator
    auth_service = AuthService(database_locator)
    services = PlatformServices(database_locator)

    # 数据库中的平台/LLM 配置优先生效，随后重新读取统一配置对象。
    apply_platform_runtime_env(services.settings)
    config = get_global_config()
    set_trace_sink(services.llm.save_call_trace)

    ai_learned_path = config.data_normalized_dir / "ai-learned.jsonl"
    index = LocalQuestionIndex.from_jsonl_files((config.index_path_resolved, ai_learned_path))
    service = build_answer_service(
        index=index,
        ai_learned_path=ai_learned_path,
        settings_service=services.settings,
        model_management_service=services.llm,
    )

    return create_app(
        service,
        auth_service=auth_service,
        platform_services=services,
        require_auth=config.require_auth,
        lifespan=runtime_lifespan,
    )


@asynccontextmanager
async def runtime_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """仅在真实运行时启动生图队列，测试应用不创建网络任务。"""

    image_worker = ImageGenerationWorker(app.state.services.image_generation)
    app.state.image_generation_worker = image_worker
    await image_worker.start()
    try:
        yield
    finally:
        await image_worker.stop()


def create_runtime_app() -> FastAPI:
    """提供给 uvicorn 的工厂入口。"""

    load_local_env()
    configure_external_loggers()
    app = build_runtime_app()
    config = get_global_config()
    log_event(
        "service_start",
        {
            "host": config.host,
            "port": config.port,
            "require_auth": config.require_auth,
            "server": "fastapi",
            "reload": config.reload,
            "entrypoint": "uvicorn-factory",
        },
    )
    return app


def build_answer_service(
    *,
    index: LocalQuestionIndex,
    ai_learned_path: Path,
    settings_service: SettingsService | None = None,
    model_management_service: LlmManagementService | None = None,
) -> AnswerService:
    """按统一配置构建答题服务。"""

    provider, llm_answer_cache = build_provider_stack(
        ai_learned_path,
        settings_service=settings_service,
        model_management_service=model_management_service,
    )
    config = get_global_config()
    llm_runtime = (
        settings_service.get_llm_runtime_config() if settings_service is not None else {}
    )
    system_config = settings_service.get_system_config() if settings_service is not None else {}
    allow_model_fallback = (
        bool_from_config(llm_runtime.get("llm_fallback"), default=config.llm_fallback)
        and provider is not None
    )
    explain_local_matches = bool_from_config(
        llm_runtime.get("llm_explain"),
        default=config.llm_explain,
    )
    service = AnswerService(
        index,
        answer_retrieval_tool=LocalRagTool(index),
        model_provider=provider,
        allow_model_fallback=allow_model_fallback,
        explain_local_matches=explain_local_matches,
        no_local_bank_mode=bool_from_config(
            llm_runtime.get("no_local_bank_mode"),
            default=config.no_local_bank_mode,
        ),
        llm_answer_cache=llm_answer_cache,
        trusted_confidence_threshold=float_from_config(
            llm_runtime.get("llm_cache_min_confidence")
            or llm_runtime.get("ai_cache_min_confidence"),
            default=config.llm_cache_min_confidence,
        ),
        answer_retry_times=int_from_config(
            system_config.get("answer_retry_times"),
            default=config.answer_retry_times,
        ),
    )
    service.runtime_settings_service = settings_service
    service.model_management_service = model_management_service
    return service


def refresh_answer_service(service: AnswerService, *, ai_learned_path: Path | None = None) -> None:
    """在不重启进程的情况下刷新答题服务配置。"""

    config = get_global_config()
    settings_service = service.runtime_settings_service
    model_management_service = service.model_management_service
    path = ai_learned_path or (config.data_normalized_dir / "ai-learned.jsonl")
    provider, llm_answer_cache = build_provider_stack(
        path,
        settings_service=settings_service,
        model_management_service=model_management_service,
    )
    llm_runtime = (
        settings_service.get_llm_runtime_config() if settings_service is not None else {}
    )
    system_config = settings_service.get_system_config() if settings_service is not None else {}
    service.model_provider = provider
    service.allow_model_fallback = (
        bool_from_config(llm_runtime.get("llm_fallback"), default=config.llm_fallback)
        and provider is not None
    )
    service.explain_local_matches = bool_from_config(
        llm_runtime.get("llm_explain"),
        default=config.llm_explain,
    )
    service.no_local_bank_mode = bool_from_config(
        llm_runtime.get("no_local_bank_mode"),
        default=config.no_local_bank_mode,
    )
    service.llm_answer_cache = llm_answer_cache
    service.trusted_confidence_threshold = float_from_config(
        llm_runtime.get("llm_cache_min_confidence")
        or llm_runtime.get("ai_cache_min_confidence"),
        default=config.llm_cache_min_confidence,
    )
    service.answer_retry_times = int_from_config(
        system_config.get("answer_retry_times"),
        default=config.answer_retry_times,
    )


def load_local_env_fallback(path: Path) -> None:
    """在缺少 python-dotenv 时手动解析本地环境变量文件。"""

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def bool_from_config(value: object, *, default: bool) -> bool:
    """按常见布尔配置语义解析值。"""

    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def float_from_config(value: object, *, default: float) -> float:
    """按浮点数语义解析配置值，失败时回退默认值。"""

    if value is None or not str(value).strip():
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def int_from_config(value: object, *, default: int) -> int:
    """按正整数语义解析配置值，失败时回退默认值。"""

    if value is None or not str(value).strip():
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def apply_platform_runtime_env(settings_service: SettingsService) -> None:
    """把平台保存的系统配置同步到当前进程环境变量。"""

    for env_key, value in settings_service.runtime_env().items():
        os.environ[env_key] = value


def build_base_model_provider(
    model_management_service: LlmManagementService | None,
) -> OpenAICompatibleProvider | MultiModelProvider | None:
    """从数据库读取模型配置。"""

    members: list[OpenAICompatibleProvider] = []
    if model_management_service is not None:
        try:
            records = model_management_service.active_models()
        except Exception:
            records = []
        for record in records:
            members.append(
                OpenAICompatibleProvider(
                    base_url=record.base_url,
                    model=record.model,
                    api_key=record.api_key or None,
                    stream=record.stream,
                    max_completion_tokens=record.max_completion_tokens,
                    timeout_seconds=record.timeout_seconds,
                    model_id=record.model_id,
                    display_name=record.name,
                )
            )
    if members:
        return members[0] if len(members) == 1 else MultiModelProvider(members=tuple(members))
    return None


def build_provider_stack(
    ai_learned_path: Path,
    *,
    settings_service: SettingsService | None = None,
    model_management_service: LlmManagementService | None = None,
) -> tuple[
    OpenAICompatibleProvider | MultiModelProvider | SearchAugmentedModelProvider | None,
    LlmAnswerCache | None,
]:
    """构建模型提供者、联网搜索增强层与 LLM 学习缓存。"""

    config = get_global_config()
    llm_runtime = (
        settings_service.get_llm_runtime_config(reveal_secret=True)
        if settings_service is not None
        else {}
    )
    provider: OpenAICompatibleProvider | MultiModelProvider | SearchAugmentedModelProvider | None
    provider = build_base_model_provider(model_management_service)
    search_provider = build_search_provider(runtime_config=llm_runtime, global_config=config)
    if provider is not None and search_provider is not None:
        provider = SearchAugmentedModelProvider(
            provider,
            WebSearchTool(search_provider),
            search_first=bool_from_config(
                llm_runtime.get("search_first"),
                default=config.search_first,
            ),
            self_consistency_repeats=int_from_config(
                llm_runtime.get("self_consistency_repeats"),
                default=config.self_consistency_repeats,
            ),
            search_cache_path=(
                str(config.search_cache_path_resolved)
                if config.search_cache_path_resolved is not None
                else None
            ),
        )

    llm_answer_cache = None
    cache_enabled = bool_from_config(
        llm_runtime.get("llm_cache_enabled") or llm_runtime.get("ai_cache_enabled"),
        default=config.llm_cache_enabled,
    )
    no_local_bank = bool_from_config(
        llm_runtime.get("no_local_bank_mode"),
        default=config.no_local_bank_mode,
    )
    if provider is not None and cache_enabled and not no_local_bank:
        llm_answer_cache = LlmAnswerCache(
            ai_learned_path,
            min_confidence=float_from_config(
                llm_runtime.get("llm_cache_min_confidence")
                or llm_runtime.get("ai_cache_min_confidence"),
                default=config.llm_cache_min_confidence,
            ),
            min_confirmations=int_from_config(
                llm_runtime.get("llm_cache_min_confirmations")
                or llm_runtime.get("ai_cache_min_confirmations"),
                default=config.llm_cache_min_confirmations,
            ),
            legacy_paths=(config.legacy_ai_cache_path,),
        )
    return provider, llm_answer_cache
