"""项目统一环境配置与默认存储路径。"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_NORMALIZED_DIR = DATA_DIR / "normalized"
DATA_RUNTIME_DIR = DATA_DIR / "runtime"
DATA_LOGS_DIR = DATA_DIR / "logs"
PROMPTS_DIR = CONFIG_DIR / "prompts"

ENV_DATABASE_URL = "STQB_DATABASE_URL"
ENV_DATA_DIR = "STQB_DATA_DIR"
ENV_DATABASE_PATH = "STQB_DATABASE_PATH"
ENV_DB_POOL_SIZE = "STQB_DB_POOL_SIZE"
ENV_DB_MAX_OVERFLOW = "STQB_DB_MAX_OVERFLOW"
ENV_DB_POOL_TIMEOUT = "STQB_DB_POOL_TIMEOUT"
ENV_DB_POOL_RECYCLE = "STQB_DB_POOL_RECYCLE"
ENV_REDIS_URL = "STQB_REDIS_URL"
ENV_PUBLIC_BASE_URL = "STQB_PUBLIC_BASE_URL"
ENV_REQUIRE_AUTH = "STQB_REQUIRE_AUTH"
ENV_OCS_API_KEYS = "STQB_OCS_API_KEYS"
ENV_DEFAULT_USER_POINTS = "STQB_DEFAULT_USER_POINTS"
ENV_ANSWER_RETRY_TIMES = "STQB_ANSWER_RETRY_TIMES"
ENV_LOG_PATH = "STQB_LOG_PATH"
ENV_CONSOLE_LOG = "STQB_CONSOLE_LOG"
ENV_CONSOLE_LOG_LEVEL = "STQB_CONSOLE_LOG_LEVEL"
ENV_HOST = "STQB_HOST"
ENV_PORT = "STQB_PORT"
ENV_RELOAD = "STQB_RELOAD"
ENV_INDEX_PATH = "STQB_INDEX_PATH"
ENV_ANSWER_RULES_PATH = "STQB_ANSWER_RULES_PATH"
ENV_REVIEWED_RESULTS_DIR = "STQB_REVIEWED_RESULTS_DIR"
ENV_REVIEWED_RESULTS_GLOB = "STQB_REVIEWED_RESULTS_GLOB"
ENV_REVIEWED_ANSWER_OVERRIDES_PATH = "STQB_REVIEWED_ANSWER_OVERRIDES_PATH"
ENV_LLM_PROXY = "STQB_LLM_PROXY"
ENV_LLM_FALLBACK = "STQB_LLM_FALLBACK"
ENV_LLM_EXPLAIN = "STQB_LLM_EXPLAIN"
ENV_ALLOW_KNOWN_RULES = "STQB_ALLOW_KNOWN_RULES"
ENV_NO_LOCAL_BANK_MODE = "STQB_NO_LOCAL_BANK_MODE"
ENV_SEARCH_FIRST = "STQB_SEARCH_FIRST"
ENV_SELF_CONSISTENCY_REPEATS = "STQB_SELF_CONSISTENCY_REPEATS"
ENV_WEB_SEARCH_PROVIDER = "STQB_WEB_SEARCH_PROVIDER"
ENV_SEARCH_PROXY = "STQB_SEARCH_PROXY"
ENV_SEARCH_BROWSER_PATH = "STQB_SEARCH_BROWSER_PATH"
ENV_SEARCH_CACHE_PATH = "STQB_SEARCH_CACHE_PATH"
ENV_SEARCH_PAGE_CACHE_PATH = "STQB_SEARCH_PAGE_CACHE_PATH"
ENV_GOOGLE_SEARCH_API_KEY = "STQB_GOOGLE_SEARCH_API_KEY"
ENV_GOOGLE_SEARCH_CX = "STQB_GOOGLE_SEARCH_CX"
ENV_BAIDU_SEARCH_API_KEY = "STQB_BAIDU_SEARCH_API_KEY"
ENV_LLM_CACHE_ENABLED = "STQB_LLM_CACHE_ENABLED"
ENV_LLM_CACHE_MIN_CONFIDENCE = "STQB_LLM_CACHE_MIN_CONFIDENCE"
ENV_LLM_CACHE_MIN_CONFIRMATIONS = "STQB_LLM_CACHE_MIN_CONFIRMATIONS"
ENV_GIT_UPDATE_ENABLED = "STQB_GIT_UPDATE_ENABLED"
ENV_GIT_REPO_DIR = "STQB_GIT_REPO_DIR"
ENV_GIT_REMOTE = "STQB_GIT_REMOTE"
ENV_GIT_REMOTE_URL = "STQB_GIT_REMOTE_URL"
ENV_GIT_BRANCH = "STQB_GIT_BRANCH"
ENV_GIT_UPDATE_AUTO_RESTART = "STQB_GIT_UPDATE_AUTO_RESTART"


class GlobalConfig(BaseModel):
    """统一承载所有来自 `.env` / 环境变量的部署级配置。"""

    # 数据库连接配置：优先完整 URL，其次本地 SQLite 文件路径。
    database_url: str = ""
    data_dir_path: str = "data"
    database_path: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # 状态与会话存储：未配置 Redis 时回退为进程内存实现。
    redis_url: str = ""

    # 基础服务行为：鉴权、外部访问地址与静态 OCS 密钥。
    public_base_url: str = ""
    require_auth: bool = False
    ocs_api_keys: tuple[str, ...] = ()
    default_user_points: int = 0
    answer_retry_times: int = 3

    # 运行时日志：JSONL 文件、控制台开关与日志级别统一在这里声明。
    log_path: str = ""
    console_log: bool = True
    console_log_level: str = "INFO"

    # 服务启动参数：保持 uvicorn 工厂模式下的环境兼容入口。
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = False

    # 本地题库导入源与结果页输入路径：统一使用 data 目录作为默认生产落点。
    index_path: str = ""
    answer_rules_path: str = ""
    reviewed_results_dir: str = ""
    reviewed_results_glob: str = "*.html"
    reviewed_answer_overrides_path: str = ""

    # 模型请求代理仍属于部署级参数；具体模型地址、名称与密钥统一由数据库管理。
    llm_proxy: str = ""

    # 联网搜索与 provider 兼容配置：数据库/UI 配置同步到进程环境后仍走这里读取。
    web_search_provider: str = ""
    search_proxy: str = ""
    search_browser_path: str = ""
    search_cache_path: str = ""
    search_page_cache_path: str = ""
    google_search_api_key: str = ""
    google_search_cx: str = ""
    baidu_search_api_key: str = ""

    # LLM 答题兼容开关：数据库配置缺位时作为兜底来源，不改变现有平台配置归属。
    llm_fallback: bool = False
    llm_explain: bool = False
    allow_known_rules: bool = True
    no_local_bank_mode: bool = False
    search_first: bool = False
    self_consistency_repeats: int = 1
    llm_cache_enabled: bool = True
    llm_cache_min_confidence: float = 0.95
    llm_cache_min_confirmations: int = 2

    # Git 更新检测：只属于部署/运维级配置，不进入数据库系统设置表。
    git_update_enabled: bool = True
    git_repo_dir: str = ""
    git_remote: str = "origin"
    git_remote_url: str = ""
    git_branch: str = ""
    git_update_auto_restart: bool = False

    @property
    def project_root(self) -> Path:
        """返回项目根目录。"""
        return PROJECT_ROOT

    @property
    def src_root(self) -> Path:
        """返回源码根目录。"""
        return SRC_ROOT

    @property
    def config_dir(self) -> Path:
        """返回可提交静态配置目录。"""
        return CONFIG_DIR

    @property
    def data_dir(self) -> Path:
        """返回运行数据根目录。"""
        return self.resolve_path(self.data_dir_path, default=DATA_DIR)

    @property
    def data_raw_dir(self) -> Path:
        """返回原始题库与导入数据目录。"""
        return self.data_dir / "raw"

    @property
    def data_normalized_dir(self) -> Path:
        """返回标准化题库目录。"""
        return self.data_dir / "normalized"

    @property
    def data_runtime_dir(self) -> Path:
        """返回数据库、缓存等运行时数据目录。"""
        return self.data_dir / "runtime"

    @property
    def data_logs_dir(self) -> Path:
        """返回结构化日志目录。"""
        return self.data_dir / "logs"

    @property
    def prompts_dir(self) -> Path:
        """返回可提交的大模型提示词模板目录。"""
        return self.config_dir / "prompts"

    @property
    def ocs_images_dir(self) -> Path:
        """返回 OCS 题目图片运行时存储目录。"""
        return self.data_dir / "images" / "ocs"

    @property
    def database_locator(self) -> str:
        """返回传给仓储层的数据库定位值。"""
        return self.database_url.strip() or str(self.database_path_resolved)

    @property
    def database_path_resolved(self) -> Path:
        """返回 SQLite 数据库文件路径。"""
        return self.resolve_path(
            self.database_path, default=self.data_runtime_dir / "study-qb.sqlite3"
        )

    @property
    def log_path_resolved(self) -> Path:
        """返回运行时日志 JSONL 文件路径。"""
        return self.resolve_path(self.log_path, default=self.data_logs_dir / "service.jsonl")

    @property
    def index_path_resolved(self) -> Path:
        """返回基础题库 JSONL 文件路径。"""
        return self.resolve_path(
            self.index_path,
            default=self.data_normalized_dir / "verified.jsonl",
        )

    @property
    def legacy_llm_cache_path(self) -> Path:
        """返回旧版 JSON 缓存迁移源路径。"""
        return self.data_runtime_dir / "llm-answer-cache.json"

    @property
    def legacy_ai_cache_path(self) -> Path:
        """兼容旧命名，返回旧版 JSON 缓存迁移源路径。"""
        return self.legacy_llm_cache_path

    @property
    def reviewed_results_dir_resolved(self) -> Path | None:
        """返回已批改结果页目录。"""
        return self.resolve_optional_path(self.reviewed_results_dir)

    @property
    def reviewed_answer_overrides_path_resolved(self) -> Path | None:
        """返回批改答案覆盖文件路径。"""
        return self.resolve_optional_path(self.reviewed_answer_overrides_path)

    @property
    def answer_rules_path_resolved(self) -> Path | None:
        """返回外部答案规则文件路径。"""
        return self.resolve_optional_path(self.answer_rules_path)

    @property
    def search_cache_path_resolved(self) -> Path | None:
        """返回联网搜索缓存文件路径。"""
        return self.resolve_optional_path(self.search_cache_path)

    @property
    def search_page_cache_path_resolved(self) -> Path | None:
        """返回浏览器页面摘录缓存文件路径。"""
        return self.resolve_optional_path(self.search_page_cache_path)

    @property
    def search_browser_path_resolved(self) -> Path | None:
        """返回显式配置的浏览器可执行文件路径。"""
        return self.resolve_optional_path(self.search_browser_path)

    @property
    def git_repo_dir_resolved(self) -> Path:
        """返回项目更新检测使用的仓库目录。"""
        if not self.git_repo_dir.strip():
            return self.project_root
        return self.resolve_path(self.git_repo_dir, default=self.project_root)

    def resolve_path(self, value: str | Path | None, *, default: str | Path) -> Path:
        """把相对路径统一解析到项目根目录下。"""
        raw = str(value or "").strip()
        base = Path(default)
        candidate = Path(raw) if raw else base
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        return candidate.resolve()

    def resolve_optional_path(self, value: str | Path | None) -> Path | None:
        """把可选路径解析到项目根目录；空值直接返回 None。"""
        raw = str(value or "").strip()
        if not raw:
            return None
        return self.resolve_path(raw, default=raw)


def load_global_config() -> GlobalConfig:
    """从当前进程环境中加载一份最新的全局配置。"""
    return GlobalConfig(
        database_url=env_text(ENV_DATABASE_URL),
        data_dir_path=env_text(ENV_DATA_DIR, "data"),
        database_path=env_text(ENV_DATABASE_PATH),
        db_pool_size=env_int(ENV_DB_POOL_SIZE, 10),
        db_max_overflow=env_int(ENV_DB_MAX_OVERFLOW, 20),
        db_pool_timeout=env_int(ENV_DB_POOL_TIMEOUT, 30),
        db_pool_recycle=env_int(ENV_DB_POOL_RECYCLE, 1800),
        redis_url=env_text(ENV_REDIS_URL),
        public_base_url=env_text(ENV_PUBLIC_BASE_URL).rstrip("/"),
        require_auth=env_bool(ENV_REQUIRE_AUTH, False),
        ocs_api_keys=env_csv(ENV_OCS_API_KEYS),
        default_user_points=env_int(ENV_DEFAULT_USER_POINTS, 0),
        answer_retry_times=max(0, min(env_int(ENV_ANSWER_RETRY_TIMES, 3), 10)),
        log_path=env_text(ENV_LOG_PATH),
        console_log=env_bool(ENV_CONSOLE_LOG, True),
        console_log_level=env_text(ENV_CONSOLE_LOG_LEVEL, "INFO"),
        host=env_text(ENV_HOST, "127.0.0.1"),
        port=env_int(ENV_PORT, 8765),
        reload=env_bool(ENV_RELOAD, False),
        index_path=env_text(ENV_INDEX_PATH),
        answer_rules_path=env_text(ENV_ANSWER_RULES_PATH),
        reviewed_results_dir=env_text(ENV_REVIEWED_RESULTS_DIR),
        reviewed_results_glob=env_text(ENV_REVIEWED_RESULTS_GLOB, "*.html"),
        reviewed_answer_overrides_path=env_text(ENV_REVIEWED_ANSWER_OVERRIDES_PATH),
        llm_proxy=env_text(ENV_LLM_PROXY),
        web_search_provider=env_text(ENV_WEB_SEARCH_PROVIDER),
        search_proxy=env_text(ENV_SEARCH_PROXY),
        search_browser_path=env_text(ENV_SEARCH_BROWSER_PATH),
        search_cache_path=env_text(ENV_SEARCH_CACHE_PATH),
        search_page_cache_path=env_text(ENV_SEARCH_PAGE_CACHE_PATH),
        google_search_api_key=env_text(ENV_GOOGLE_SEARCH_API_KEY),
        google_search_cx=env_text(ENV_GOOGLE_SEARCH_CX),
        baidu_search_api_key=env_text(ENV_BAIDU_SEARCH_API_KEY),
        llm_fallback=env_bool(ENV_LLM_FALLBACK, False),
        llm_explain=env_bool(ENV_LLM_EXPLAIN, False),
        allow_known_rules=env_bool(ENV_ALLOW_KNOWN_RULES, True),
        no_local_bank_mode=env_bool(ENV_NO_LOCAL_BANK_MODE, False),
        search_first=env_bool(ENV_SEARCH_FIRST, False),
        self_consistency_repeats=env_int(ENV_SELF_CONSISTENCY_REPEATS, 1),
        llm_cache_enabled=env_bool(ENV_LLM_CACHE_ENABLED, True),
        llm_cache_min_confidence=env_float(ENV_LLM_CACHE_MIN_CONFIDENCE, 0.95),
        llm_cache_min_confirmations=env_int(ENV_LLM_CACHE_MIN_CONFIRMATIONS, 2),
        git_update_enabled=env_bool(ENV_GIT_UPDATE_ENABLED, True),
        git_repo_dir=env_text(ENV_GIT_REPO_DIR),
        git_remote=env_text(ENV_GIT_REMOTE, "origin"),
        git_remote_url=env_text(ENV_GIT_REMOTE_URL),
        git_branch=env_text(ENV_GIT_BRANCH),
        git_update_auto_restart=env_bool(ENV_GIT_UPDATE_AUTO_RESTART, False),
    )


def get_global_config() -> GlobalConfig:
    """返回当前进程环境对应的全局配置。"""
    return load_global_config()


def env_text(name: str, default: str = "") -> str:
    """读取文本环境变量。"""
    value = os.getenv(name)
    return value.strip() if value is not None else default


def env_bool(name: str, default: bool = False) -> bool:
    """按常见布尔语义读取环境变量。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def env_int(name: str, default: int) -> int:
    """按整数语义读取环境变量。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    """按浮点数语义读取环境变量。"""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def env_csv(name: str) -> tuple[str, ...]:
    """把逗号分隔的环境变量读取为稳定元组。"""
    raw = env_text(name)
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())
