"""文本生图任务的业务编排、积分结算与私有资产生命周期。"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from threading import RLock

from ...llm.image_generation import (
    ImageGenerationProvider,
    ImageGenerationProviderError,
    ImageGenerationRequest,
    OpenAIChatImageGenerationProvider,
    OpenAIImageGenerationProvider,
)
from ...logger import log_event
from ...media.generated_images import (
    GeneratedImageError,
    delete_generated_image,
    generated_image_path,
    store_generated_image,
)
from ...storage.repositories.image_generation import (
    ImageGenerationRepository,
    ImageGenerationRepositoryError,
)
from ..base import PlatformDomainService
from .records import (
    ImageGenerationAssetRecord,
    ImageGenerationJobRecord,
    ImageGenerationModelRecord,
    ImageGenerationTraceRecord,
)


DEFAULT_IMAGE_CAPABILITIES = "text-to-image,1024x1024,1024x1536,1536x1024"
MAX_PROMPT_LENGTH = 4_000
SUPPORTED_IMAGE_PROVIDERS = frozenset({"openai-images", "openai-chat-image"})


class ImageGenerationError(RuntimeError):
    """生图领域的可预期业务错误。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def build_image_generation_provider(
    model: ImageGenerationModelRecord,
) -> ImageGenerationProvider:
    """根据已保存模型配置创建对应提供商适配器。"""

    if model.provider == "openai-images":
        return OpenAIImageGenerationProvider(
            base_url=model.base_url,
            model=model.model,
            api_key=model.api_key,
            timeout_seconds=model.timeout_seconds,
        )
    if model.provider == "openai-chat-image":
        return OpenAIChatImageGenerationProvider(
            base_url=model.base_url,
            model=model.model,
            api_key=model.api_key,
            timeout_seconds=model.timeout_seconds,
        )
    raise ImageGenerationError(
        "UNSUPPORTED_IMAGE_PROVIDER", f"暂不支持的生图提供商: {model.provider}", http_status=400
    )


class ImageGenerationService(PlatformDomainService):
    """统一管理模型配置、异步任务、预扣积分与生成资产。"""

    def __init__(
        self,
        repository: ImageGenerationRepository,
        settings_service,
        lock: RLock,
        *,
        provider_factory: Callable[[ImageGenerationModelRecord], ImageGenerationProvider] = (
            build_image_generation_provider
        ),
    ) -> None:
        super().__init__(repository, lock)
        self.settings_service = settings_service
        self.provider_factory = provider_factory

    def list_models(self) -> list[dict]:
        """列出所有生图模型，密钥不属于任何读接口。"""

        with self.lock:
            return [item.to_dict() for item in self.repository.list_models()]

    def create_model(
        self,
        *,
        name: str,
        provider: str,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        status: str = "active",
        capabilities: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        """创建独立的生图模型配置。"""

        now = time.time()
        normalized_api_key = self._validate_api_key(api_key)
        if not normalized_api_key:
            raise ImageGenerationError("INVALID_INPUT", "请填写生图 API Key")
        record = ImageGenerationModelRecord(
            model_id=secrets.token_hex(12),
            name=self._validate_model_name(name),
            provider=self._validate_provider(provider),
            base_url=self._validate_base_url(base_url),
            model=self._validate_model_identifier(model),
            api_key=normalized_api_key,
            timeout_seconds=self._validate_timeout(timeout_seconds),
            status=self._validate_model_status(status),
            capabilities=self._normalize_capabilities(capabilities),
            created_at=now,
            updated_at=now,
        )
        with self.lock:
            return self.repository.save_model(record).to_dict()

    def update_model(self, model_id: str, values: dict) -> dict:
        """更新生图模型，空密钥表示保持原值。"""

        with self.lock:
            record = self.repository.get_model(model_id)
            if record is None:
                raise ImageGenerationError("IMAGE_MODEL_NOT_FOUND", "生图模型不存在", http_status=404)
            if "name" in values:
                record.name = self._validate_model_name(values["name"])
            if "provider" in values:
                record.provider = self._validate_provider(values["provider"])
            if "base_url" in values:
                record.base_url = self._validate_base_url(values["base_url"])
            if "model" in values:
                record.model = self._validate_model_identifier(values["model"])
            if "api_key" in values and str(values["api_key"] or "").strip():
                record.api_key = self._validate_api_key(values["api_key"])
            if "timeout_seconds" in values:
                record.timeout_seconds = self._validate_timeout(values["timeout_seconds"])
            if "status" in values:
                record.status = self._validate_model_status(values["status"])
            if "capabilities" in values:
                record.capabilities = self._normalize_capabilities(values["capabilities"])
            record.updated_at = time.time()
            return self.repository.save_model(record).to_dict()

    def delete_model(self, model_id: str) -> bool:
        """删除没有活动任务的生图模型。"""

        try:
            with self.lock:
                return self.repository.delete_model(model_id)
        except ImageGenerationRepositoryError as exc:
            raise self._repository_error(exc) from exc

    def create_job(
        self,
        *,
        user_id: str,
        username: str,
        prompt: str,
        size: str = "",
        idempotency_key: str = "",
    ) -> tuple[dict, bool]:
        """提交一条生图任务，并在同一事务中预扣当前单张积分。"""

        normalized_prompt = self._validate_prompt(prompt)
        with self.lock:
            model = self.repository.get_active_model()
            if model is None:
                raise ImageGenerationError(
                    "IMAGE_GENERATION_UNAVAILABLE", "当前没有可用的生图模型", http_status=503
                )
            selected_size = self._validate_size(size, model)
            policy = self.settings_service.get_image_generation_policy()
            now = time.time()
            normalized_key = self._normalize_idempotency_key(idempotency_key)
            expires_at = (
                now + policy["retention_days"] * 86_400
                if policy["retention_days"] > 0
                else 0.0
            )
            record = ImageGenerationJobRecord(
                job_id=secrets.token_hex(12),
                user_id=user_id,
                username=username,
                prompt=normalized_prompt,
                size=selected_size,
                model_id=model.model_id,
                model_name=model.name,
                model_snapshot=json.dumps(
                    {
                        "provider": model.provider,
                        "base_url": model.base_url,
                        "model": model.model,
                        "timeout_seconds": model.timeout_seconds,
                        "capabilities": self._capabilities(model),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                status="queued",
                points_cost=policy["points"],
                reservation_order_id=secrets.token_hex(12),
                idempotency_key=normalized_key,
                error_code="",
                error_message="",
                created_at=now,
                started_at=0.0,
                completed_at=0.0,
                updated_at=now,
                expires_at=expires_at,
            )
            try:
                job, created = self.repository.create_job_with_reservation(
                    record,
                    active_limit=policy["max_active_jobs"],
                    daily_limit=policy["daily_limit"],
                )
            except ImageGenerationRepositoryError as exc:
                raise self._repository_error(exc) from exc
        log_event(
            "image_generation_job_submitted",
            {
                "job_id": job.job_id,
                "user_id": user_id,
                "model_id": job.model_id,
                "size": job.size,
                "points_cost": job.points_cost,
                "idempotent_replay": not created,
                "prompt_length": len(normalized_prompt),
            },
        )
        return self._job_payload(job), created

    def process_next_job(self) -> bool:
        """执行一条队列任务；任何失败均由本方法负责退款。"""

        now = time.time()
        job = self.repository.claim_next_job(now)
        if job is None:
            return False
        started = time.monotonic()
        model = self.repository.get_model(job.model_id)
        if model is None:
            self._finish_failure(
                job,
                status="failed",
                code="IMAGE_MODEL_UNAVAILABLE",
                message="任务使用的生图模型已不可用",
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
            return True
        try:
            execution_model = self._execution_model(job, model)
        except ImageGenerationError as exc:
            self._finish_failure(
                job,
                status="failed",
                code=exc.code,
                message=exc.message,
                elapsed_ms=(time.monotonic() - started) * 1000,
                model=model,
            )
            return True
        stored_key = ""
        try:
            provider = self.provider_factory(execution_model)
            generated = provider.generate(
                ImageGenerationRequest(prompt=job.prompt, size=job.size, request_id=job.job_id)
            )
            stored = store_generated_image(asset_id=secrets.token_hex(16), content=generated.content)
            stored_key = stored.storage_key
            asset = ImageGenerationAssetRecord(
                asset_id=stored.storage_key.rsplit(".", 1)[0],
                job_id=job.job_id,
                storage_key=stored.storage_key,
                content_hash=stored.content_hash,
                mime_type=stored.mime_type,
                width=stored.width,
                height=stored.height,
                byte_size=stored.byte_size,
                created_at=time.time(),
            )
            completed = self.repository.complete_job(job.job_id, asset, completed_at=time.time())
            stored_key = ""
        except ImageGenerationProviderError as exc:
            if stored_key:
                delete_generated_image(stored_key)
            self._finish_failure(
                job,
                status="rejected" if exc.code == "CONTENT_POLICY_REJECTED" else "failed",
                code=exc.code,
                message=exc.message,
                elapsed_ms=(time.monotonic() - started) * 1000,
                model=execution_model,
            )
        except GeneratedImageError as exc:
            if stored_key:
                delete_generated_image(stored_key)
            self._finish_failure(
                job,
                status="failed",
                code="INVALID_GENERATED_IMAGE",
                message=str(exc),
                elapsed_ms=(time.monotonic() - started) * 1000,
                model=execution_model,
            )
        except Exception:
            if stored_key:
                delete_generated_image(stored_key)
            self._finish_failure(
                job,
                status="failed",
                code="IMAGE_GENERATION_FAILED",
                message="生图服务执行失败",
                elapsed_ms=(time.monotonic() - started) * 1000,
                model=execution_model,
                trace_error="生图服务发生未预期错误",
            )
        else:
            try:
                self._save_trace(
                    completed,
                    execution_model,
                    ok=True,
                    elapsed_ms=(time.monotonic() - started) * 1000,
                    provider_request_id=generated.provider_request_id,
                )
            except Exception as exc:
                log_event(
                    "image_generation_trace_write_failed",
                    {"job_id": completed.job_id, "error_type": type(exc).__name__},
                )
            log_event(
                "image_generation_job_completed",
                {
                    "job_id": completed.job_id,
                    "model_id": completed.model_id,
                    "asset_id": asset.asset_id,
                    "byte_size": asset.byte_size,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
        return True

    def recover_abandoned_jobs(self, *, max_running_seconds: float = 300.0) -> int:
        """启动时结算异常退出遗留的运行任务，避免积分永久冻结。"""

        recovered = 0
        before = time.time() - max(1.0, max_running_seconds)
        for job_id in self.repository.stale_running_job_ids(before=before):
            job = self.repository.get_job(job_id)
            if job is None:
                continue
            if self._finish_failure(
                job,
                status="failed",
                code="WORKER_INTERRUPTED",
                message="服务重启前的生图任务未完成，积分已自动退还",
                elapsed_ms=0.0,
                expected_status="running",
            ):
                recovered += 1
        return recovered

    def cleanup_expired_assets(self) -> int:
        """按保留策略撤销过期资产访问并删除文件。"""

        assets = self.repository.expired_job_assets(before=time.time())
        for asset in assets:
            delete_generated_image(asset.storage_key)
        return len(assets)

    def get_capabilities(self, *, user_points: int) -> dict:
        """返回用户页面初始化所需的可用模型、限额和余额。"""

        with self.lock:
            model = self.repository.get_active_model()
            policy = self.settings_service.get_image_generation_policy()
            return {
                "available": model is not None,
                "model_name": model.name if model else "",
                "sizes": self._sizes(model) if model else [],
                "points_per_image": policy["points"],
                "max_active_jobs": policy["max_active_jobs"],
                "daily_limit": policy["daily_limit"],
                "retention_days": policy["retention_days"],
                "balance": max(0, int(user_points)),
            }

    def get_job(self, job_id: str) -> dict:
        """读取任务及其仍可访问资产。"""

        job = self.repository.get_job(job_id)
        if job is None:
            raise ImageGenerationError("JOB_NOT_FOUND", "生图任务不存在", http_status=404)
        return self._job_payload(job)

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        status: str = "",
        page: int = 1,
        limit: int = 30,
    ) -> dict:
        """分页返回任务历史。"""

        safe_page = max(1, int(page))
        safe_limit = max(1, min(int(limit), 100))
        records = self.repository.list_jobs(
            user_id=user_id,
            status=status.strip(),
            offset=(safe_page - 1) * safe_limit,
            limit=safe_limit,
        )
        return {
            "jobs": [self._job_payload(item) for item in records],
            "total": self.repository.count_jobs(user_id=user_id, status=status.strip()),
            "page": safe_page,
            "limit": safe_limit,
        }

    def ensure_job_owner(self, job_id: str, *, user_id: str, allow_admin: bool) -> dict:
        """读取任务并校验调用者是否拥有读取权限。"""

        payload = self.get_job(job_id)
        if not allow_admin and payload["user_id"] != user_id:
            raise ImageGenerationError("JOB_FORBIDDEN", "无权访问该生图任务", http_status=403)
        return payload

    def asset_path(self, job_id: str, asset_id: str) -> tuple[dict, str]:
        """返回已授权任务的私有资产信息与受控磁盘路径。"""

        asset = self.repository.get_asset(job_id, asset_id)
        if asset is None:
            raise ImageGenerationError("ASSET_NOT_FOUND", "生成图片不存在或已过期", http_status=404)
        path = generated_image_path(asset.storage_key)
        if path is None or not path.is_file():
            raise ImageGenerationError("ASSET_NOT_FOUND", "生成图片文件不存在", http_status=404)
        return asset.to_dict(), str(path)

    def delete_or_cancel_job(self, job_id: str, *, user_id: str, allow_admin: bool) -> dict:
        """取消排队任务或删除终态任务，运行中任务不允许盲目中断。"""

        job = self.repository.get_job(job_id)
        if job is None:
            raise ImageGenerationError("JOB_NOT_FOUND", "生图任务不存在", http_status=404)
        if not allow_admin and job.user_id != user_id:
            raise ImageGenerationError("JOB_FORBIDDEN", "无权操作该生图任务", http_status=403)
        if job.status == "queued":
            try:
                cancelled = self.repository.fail_job_and_refund(
                    job_id,
                    status="cancelled",
                    error_code="CANCELLED",
                    error_message="用户取消了排队中的生图任务，积分已退还",
                    completed_at=time.time(),
                    expected_status="queued",
                )
            except ImageGenerationRepositoryError as exc:
                raise self._repository_error(exc) from exc
            return self._job_payload(cancelled)
        if job.status == "running":
            raise ImageGenerationError(
                "JOB_RUNNING",
                "任务正在提交给生图服务，完成后才能删除",
                http_status=409,
            )
        try:
            deleted, storage_keys = self.repository.delete_job(job_id, now=time.time())
        except ImageGenerationRepositoryError as exc:
            raise self._repository_error(exc) from exc
        for storage_key in storage_keys:
            delete_generated_image(storage_key)
        return self._job_payload(deleted)

    def list_traces(
        self,
        *,
        job_id: str = "",
        model_id: str = "",
        page: int = 1,
        limit: int = 100,
    ) -> dict:
        """分页读取管理端调用追溯。"""

        safe_page = max(1, int(page))
        safe_limit = max(1, min(int(limit), 500))
        traces = self.repository.list_traces(
            job_id=job_id.strip(),
            model_id=model_id.strip(),
            offset=(safe_page - 1) * safe_limit,
            limit=safe_limit,
        )
        return {
            "traces": [item.to_dict() for item in traces],
            "total": self.repository.count_traces(
                job_id=job_id.strip(), model_id=model_id.strip()
            ),
            "page": safe_page,
            "limit": safe_limit,
        }

    def stats(self) -> dict:
        """返回生图管理摘要。"""

        return self.repository.stats()

    def test_model(self, model_id: str) -> dict:
        """执行一次明确触发的连通性测试，响应图片不会保存或展示。"""

        model = self.repository.get_model(model_id)
        if model is None:
            raise ImageGenerationError("IMAGE_MODEL_NOT_FOUND", "生图模型不存在", http_status=404)
        provider = self.provider_factory(model)
        started = time.monotonic()
        try:
            result = provider.generate(
                ImageGenerationRequest(
                    prompt="A small blue geometric square on a plain white background.",
                    size=self._sizes(model)[0],
                    request_id=f"test-{model_id}",
                )
            )
            return {
                "ok": True,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "provider_request_id": result.provider_request_id,
            }
        except ImageGenerationProviderError as exc:
            return {
                "ok": False,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "error_code": exc.code,
                "error": exc.message,
            }
        except Exception:
            return {
                "ok": False,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "error_code": "IMAGE_GENERATION_FAILED",
                "error": "生图模型测试失败",
            }

    def _finish_failure(
        self,
        job: ImageGenerationJobRecord,
        *,
        status: str,
        code: str,
        message: str,
        elapsed_ms: float,
        model: ImageGenerationModelRecord | None = None,
        trace_error: str = "",
        expected_status: str | None = None,
    ) -> bool:
        """写入失败追溯，退款并记录不含提示词的运行事件。"""

        try:
            completed = self.repository.fail_job_and_refund(
                job.job_id,
                status=status,
                error_code=code,
                error_message=message,
                completed_at=time.time(),
                expected_status=expected_status,
            )
        except ImageGenerationRepositoryError as exc:
            log_event(
                "image_generation_failure_state_changed",
                {"job_id": job.job_id, "error_code": exc.code},
            )
            return False
        try:
            self._save_trace(
                completed,
                model,
                ok=False,
                elapsed_ms=elapsed_ms,
                error_code=code,
                # 调用追溯只保留稳定的错误分类，避免第三方适配器意外写入请求细节。
                error=trace_error or "生图任务执行失败",
            )
        except Exception as exc:
            log_event(
                "image_generation_trace_write_failed",
                {"job_id": completed.job_id, "error_type": type(exc).__name__},
            )
        log_event(
            "image_generation_job_failed",
            {
                "job_id": completed.job_id,
                "model_id": completed.model_id,
                "status": status,
                "error_code": code,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        return True

    def _execution_model(
        self,
        job: ImageGenerationJobRecord,
        current_model: ImageGenerationModelRecord,
    ) -> ImageGenerationModelRecord:
        """用任务提交时的非敏感模型快照执行，凭据只从受控模型记录读取。

        管理员后续切换启用模型或修改其地址不能让已排队任务隐式切换供应商；
        但 API Key 不复制到任务快照，避免增加密钥持久化范围。
        """

        try:
            snapshot = json.loads(job.model_snapshot)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ImageGenerationError(
                "MODEL_SNAPSHOT_INVALID", "生图任务的模型快照无效"
            ) from exc
        if not isinstance(snapshot, dict):
            raise ImageGenerationError("MODEL_SNAPSHOT_INVALID", "生图任务的模型快照无效")
        api_key = self._validate_api_key(current_model.api_key)
        if not api_key:
            raise ImageGenerationError("IMAGE_MODEL_UNAVAILABLE", "生图模型缺少 API Key", http_status=503)
        try:
            return ImageGenerationModelRecord(
                model_id=current_model.model_id,
                name=job.model_name or current_model.name,
                provider=self._validate_provider(snapshot.get("provider")),
                base_url=self._validate_base_url(snapshot.get("base_url")),
                model=self._validate_model_identifier(snapshot.get("model")),
                api_key=api_key,
                timeout_seconds=self._validate_timeout(snapshot.get("timeout_seconds", 60.0)),
                status=current_model.status,
                capabilities=self._normalize_capabilities(snapshot.get("capabilities")),
                created_at=current_model.created_at,
                updated_at=current_model.updated_at,
            )
        except ImageGenerationError as exc:
            raise ImageGenerationError("MODEL_SNAPSHOT_INVALID", "生图任务的模型快照无效") from exc

    def _save_trace(
        self,
        job: ImageGenerationJobRecord,
        model: ImageGenerationModelRecord | None,
        *,
        ok: bool,
        elapsed_ms: float,
        provider_request_id: str = "",
        error_code: str = "",
        error: str = "",
    ) -> None:
        """持久化最小必要调用追溯，不把提示词或密钥写入其中。"""

        self.repository.save_trace(
            ImageGenerationTraceRecord(
                trace_id=secrets.token_hex(12),
                job_id=job.job_id,
                model_id=job.model_id,
                model_name=job.model_name,
                provider=model.provider if model is not None else "",
                phase="generate",
                provider_request_id=provider_request_id[:255],
                ok=ok,
                elapsed_ms=round(elapsed_ms, 2),
                error_code=error_code[:64],
                error=error[:2000],
                created_at=time.time(),
            )
        )

    def _job_payload(self, job: ImageGenerationJobRecord) -> dict:
        """构建用户与管理员共用的任务响应，不输出私有存储路径。"""

        payload = job.to_dict()
        payload["assets"] = [item.to_dict() for item in self.repository.list_assets(job.job_id)]
        return payload

    @staticmethod
    def _validate_prompt(value: object) -> str:
        prompt = str(value or "").strip()
        if not prompt:
            raise ImageGenerationError("INVALID_INPUT", "请输入图片描述", http_status=400)
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ImageGenerationError(
                "INVALID_INPUT", f"图片描述不能超过 {MAX_PROMPT_LENGTH} 个字符", http_status=400
            )
        return prompt

    @staticmethod
    def _validate_model_name(value: object) -> str:
        name = str(value or "").strip()
        if not name or len(name) > 80:
            raise ImageGenerationError("INVALID_INPUT", "生图模型名称长度必须在 1 到 80 个字符之间")
        return name

    @staticmethod
    def _validate_provider(value: object) -> str:
        provider = str(value or "").strip().lower()
        if provider not in SUPPORTED_IMAGE_PROVIDERS:
            raise ImageGenerationError(
                "INVALID_INPUT",
                "生图提供商必须是 openai-images 或 openai-chat-image",
            )
        return provider

    @staticmethod
    def _validate_base_url(value: object) -> str:
        base_url = str(value or "").strip().rstrip("/")
        if not base_url.startswith(("https://", "http://")) or len(base_url) > 512:
            raise ImageGenerationError("INVALID_INPUT", "生图接口地址必须是有效的 HTTP(S) 地址")
        return base_url

    @staticmethod
    def _validate_model_identifier(value: object) -> str:
        model = str(value or "").strip()
        if not model or len(model) > 255:
            raise ImageGenerationError("INVALID_INPUT", "请填写有效的生图模型标识")
        return model

    @staticmethod
    def _validate_api_key(value: object) -> str:
        api_key = str(value or "").strip()
        if len(api_key) > 1000 or "\n" in api_key or "\r" in api_key:
            raise ImageGenerationError("INVALID_INPUT", "生图 API Key 格式不正确")
        return api_key

    @staticmethod
    def _validate_timeout(value: object) -> float:
        try:
            timeout = float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ImageGenerationError("INVALID_INPUT", "超时时间必须是有效数字") from exc
        if timeout < 5 or timeout > 300:
            raise ImageGenerationError("INVALID_INPUT", "超时时间必须在 5 到 300 秒之间")
        return timeout

    @staticmethod
    def _validate_model_status(value: object) -> str:
        status = str(value or "").strip().lower()
        if status not in {"active", "inactive"}:
            raise ImageGenerationError("INVALID_INPUT", "生图模型状态必须为 active 或 inactive")
        return status

    @staticmethod
    def _normalize_capabilities(value: list[str] | tuple[str, ...] | object | None) -> str:
        raw_values = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
        values = [str(item).strip().lower() for item in raw_values if str(item).strip()]
        allowed = {"text-to-image", "1024x1024", "1024x1536", "1536x1024"}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ImageGenerationError(
                "INVALID_INPUT", f"不支持的生图能力: {', '.join(unknown)}"
            )
        if "text-to-image" not in values:
            values.insert(0, "text-to-image")
        if not any(item in allowed - {"text-to-image"} for item in values):
            values.append("1024x1024")
        return ",".join(dict.fromkeys(values))

    @staticmethod
    def _normalize_idempotency_key(value: object) -> str:
        key = str(value or "").strip()
        if not key:
            return secrets.token_urlsafe(24)
        if len(key) > 128 or any(character in key for character in "\r\n"):
            raise ImageGenerationError("INVALID_INPUT", "幂等键格式不正确")
        return key

    @staticmethod
    def _capabilities(model: ImageGenerationModelRecord) -> list[str]:
        return [item for item in model.capabilities.split(",") if item]

    def _sizes(self, model: ImageGenerationModelRecord) -> list[str]:
        return [
            item
            for item in self._capabilities(model)
            if item in {"1024x1024", "1024x1536", "1536x1024"}
        ] or ["1024x1024"]

    def _validate_size(self, size: object, model: ImageGenerationModelRecord) -> str:
        selected = str(size or "").strip().lower() or self._sizes(model)[0]
        if selected not in self._sizes(model):
            raise ImageGenerationError("INVALID_INPUT", "当前生图模型不支持该图片尺寸")
        return selected

    @staticmethod
    def _repository_error(exc: ImageGenerationRepositoryError) -> ImageGenerationError:
        return ImageGenerationError(exc.code, exc.message, http_status=exc.http_status)
