"""Runtime bootstrap helpers for the local FastAPI service."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from .ai_answer_cache import AIAnswerCache
from .answering import AnswerService
from .api.local_server import create_app
from .auth import AuthService
from .providers import (
    OpenAICompatibleProvider,
    SearchAugmentedModelProvider,
    build_search_provider_from_env,
)
from .runtime_log import configure_external_loggers, log_event
from .search import LocalQuestionIndex

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_INDEX = PROJECT_ROOT / "data" / "normalized" / "verified.jsonl"
DEFAULT_AI_LEARNED_BANK = PROJECT_ROOT / "data" / "normalized" / "ai-learned.jsonl"
DEFAULT_LEGACY_AI_CACHE = PROJECT_ROOT / "data" / "runtime" / "ai-answer-cache.json"
DEFAULT_USERS = PROJECT_ROOT / "data" / "runtime" / "users.json"


def load_local_env(path: Path | None = None) -> None:
    """Load `.env` and `.env.local` without overriding existing process env."""
    paths = (path,) if path is not None else (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local")
    for env_path in paths:
        if env_path is None or not env_path.exists():
            continue
        try:
            from dotenv import load_dotenv
        except ImportError:
            _load_local_env_fallback(env_path)
            continue
        load_dotenv(env_path, override=False)


def build_runtime_app() -> FastAPI:
    """Build the FastAPI app from the current runtime environment."""
    load_local_env()

    index_path = Path(os.getenv("STQB_INDEX_PATH") or DEFAULT_INDEX)
    ai_learned_path = Path(os.getenv("STQB_AI_CACHE_PATH") or DEFAULT_AI_LEARNED_BANK)

    index = LocalQuestionIndex.from_jsonl_files((index_path, ai_learned_path))

    provider = OpenAICompatibleProvider.from_env()
    search_provider = build_search_provider_from_env()
    if provider is not None and search_provider is not None:
        provider = SearchAugmentedModelProvider(provider, search_provider)

    ai_answer_cache = None
    if provider is not None and _bool_from_env(os.getenv("STQB_AI_CACHE_ENABLED"), default=True):
        ai_answer_cache = AIAnswerCache(
            ai_learned_path,
            min_confidence=_float_from_env(os.getenv("STQB_AI_CACHE_MIN_CONFIDENCE"), default=0.95),
            min_confirmations=_int_from_env(os.getenv("STQB_AI_CACHE_MIN_CONFIRMATIONS"), default=2),
            legacy_paths=(DEFAULT_LEGACY_AI_CACHE,),
        )

    allow_model_fallback = _bool_from_env(os.getenv("STQB_LLM_FALLBACK"), default=False) or provider is not None
    explain_local_matches = _bool_from_env(os.getenv("STQB_LLM_EXPLAIN"), default=False)

    service = AnswerService(
        index,
        model_provider=provider,
        allow_model_fallback=allow_model_fallback,
        explain_local_matches=explain_local_matches,
        ai_answer_cache=ai_answer_cache,
    )

    auth_service = AuthService(os.getenv("STQB_USERS_PATH") or DEFAULT_USERS)
    require_auth = _bool_from_env(os.getenv("STQB_REQUIRE_AUTH"), default=False)

    return create_app(
        service,
        auth_service=auth_service,
        require_auth=require_auth,
    )


def create_runtime_app() -> FastAPI:
    """Uvicorn factory entrypoint."""
    configure_external_loggers()
    app = build_runtime_app()
    log_event(
        "service_start",
        {
            "host": os.getenv("STQB_HOST", "127.0.0.1"),
            "port": int(os.getenv("STQB_PORT", "8765")),
            "require_auth": _bool_from_env(os.getenv("STQB_REQUIRE_AUTH"), default=False),
            "server": "fastapi",
            "reload": _bool_from_env(os.getenv("STQB_RELOAD"), default=False),
            "entrypoint": "uvicorn-factory",
        },
    )
    return app


def _load_local_env_fallback(path: Path) -> None:
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


def _bool_from_env(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _float_from_env(value: str | None, *, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int_from_env(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
