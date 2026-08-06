"""文本生图与私有图片编辑任务的编排、结算和资产生命周期。"""

from __future__ import annotations

import hashlib
import io
import json
import secrets
import time
from collections.abc import Callable, Mapping
from threading import RLock
from typing import Any

from PIL import Image

from ...llm.image_generation import (
    GeminiNativeImageGenerationProvider,
    ImageInputAsset,
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
from ...media.image_assets import PrivateImageError, validate_private_image
from ...media.generation_inputs import (
    delete_generation_input_image,
    generation_input_image_path,
    store_generation_input_image,
)
from ...storage.repositories.image_generation import (
    ImageGenerationRepository,
    ImageGenerationRepositoryError,
)
from ..base import PlatformDomainService
from .protocols import (
    GEMINI_NATIVE_PROVIDER,
    LEGACY_OPENAI_CHAT_IMAGE_PROVIDER,
    OPENAI_COMPATIBLE_IMAGES_PROVIDER,
    OPENAI_IMAGES_PROVIDER,
    ImageGenerationProtocolError,
    IMAGE_EDIT_MODES,
    MODE_TO_CAPABILITY,
    SUPPORTED_IMAGE_PROVIDERS,
    capabilities_for_protocol,
    normalize_output_options,
    normalize_protocol_config,
    operation_supported_by_protocol,
    public_input_capabilities,
    public_output_capabilities,
)
from .records import (
    ImageGenerationAssetRecord,
    ImageGenerationCapabilityCheckRecord,
    ImageGenerationInputAssetRecord,
    ImageGenerationJobInputRecord,
    ImageGenerationJobRecord,
    ImageGenerationModelRecord,
    ImageGenerationTraceRecord,
)


MAX_PROMPT_LENGTH = 4_000


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

    try:
        protocol_config = normalize_protocol_config(
            model.provider,
            model.protocol_config,
            legacy_capabilities=model.capabilities,
        )
    except ImageGenerationProtocolError as exc:
        raise ImageGenerationError(
            "INVALID_MODEL_PROTOCOL_CONFIG", "生图模型协议配置无效"
        ) from exc

    if model.provider == GEMINI_NATIVE_PROVIDER:
        return GeminiNativeImageGenerationProvider(
            base_url=model.base_url,
            model=model.model,
            api_key=model.api_key,
            timeout_seconds=model.timeout_seconds,
            auth_mode=str(protocol_config["auth_mode"]),
        )
    if model.provider in {OPENAI_IMAGES_PROVIDER, OPENAI_COMPATIBLE_IMAGES_PROVIDER}:
        return OpenAIImageGenerationProvider(
            base_url=model.base_url,
            model=model.model,
            api_key=model.api_key,
            timeout_seconds=model.timeout_seconds,
            provider_name=model.provider,
        )
    if model.provider == LEGACY_OPENAI_CHAT_IMAGE_PROVIDER:
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
        protocol_config: dict[str, object] | None = None,
    ) -> dict:
        """创建独立的生图模型配置。"""

        now = time.time()
        normalized_api_key = self._validate_api_key(api_key)
        if not normalized_api_key:
            raise ImageGenerationError("INVALID_INPUT", "请填写生图 API Key")
        normalized_provider = self._validate_provider(provider)
        normalized_protocol_config = self._normalize_protocol_config(
            normalized_provider,
            protocol_config,
            legacy_capabilities=capabilities,
        )
        record = ImageGenerationModelRecord(
            model_id=secrets.token_hex(12),
            name=self._validate_model_name(name),
            provider=normalized_provider,
            base_url=self._validate_base_url(base_url),
            model=self._validate_model_identifier(model),
            api_key=normalized_api_key,
            timeout_seconds=self._validate_timeout(timeout_seconds),
            status=self._validate_model_status(status),
            capabilities=self._serialize_capabilities(
                normalized_provider,
                normalized_protocol_config,
                legacy_capabilities=capabilities,
            ),
            created_at=now,
            updated_at=now,
            protocol_config=self._serialize_protocol_config(normalized_protocol_config),
        )
        with self.lock:
            return self.repository.save_model(record).to_dict()

    def update_model(self, model_id: str, values: dict) -> dict:
        """更新生图模型，空密钥表示保持原值。"""

        with self.lock:
            record = self.repository.get_model(model_id)
            if record is None:
                raise ImageGenerationError("IMAGE_MODEL_NOT_FOUND", "生图模型不存在", http_status=404)

            candidate_provider = self._validate_provider(values.get("provider", record.provider))
            legacy_capabilities = values.get("capabilities", record.capabilities)
            raw_protocol_config = values.get("protocol_config")
            if raw_protocol_config is None:
                raw_protocol_config = (
                    {} if candidate_provider != record.provider else record.protocol_config
                )
            normalized_protocol_config = self._normalize_protocol_config(
                candidate_provider,
                raw_protocol_config,
                legacy_capabilities=legacy_capabilities,
            )
            if "name" in values:
                record.name = self._validate_model_name(values["name"])
            if "provider" in values:
                record.provider = candidate_provider
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
            record.capabilities = self._serialize_capabilities(
                candidate_provider,
                normalized_protocol_config,
                legacy_capabilities=legacy_capabilities,
            )
            record.protocol_config = self._serialize_protocol_config(normalized_protocol_config)
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
        mode: str = "text_to_image",
        input_assets: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
        output: dict[str, object] | None = None,
        idempotency_key: str = "",
    ) -> tuple[dict, bool]:
        """提交生图或图片编辑任务，只持久化私有资产引用而不是图片内容。"""

        normalized_prompt = self._validate_prompt(prompt)
        normalized_mode = self._normalize_mode(mode)
        now = time.time()
        job_id = secrets.token_hex(12)
        references = self._normalize_input_references(
            job_id=job_id,
            raw_references=input_assets or (),
            mode=normalized_mode,
            created_at=now,
        )

        with self.lock:
            model = self.repository.get_active_model()
            if model is None:
                raise ImageGenerationError(
                    "IMAGE_GENERATION_UNAVAILABLE", "当前没有可用的生图模型", http_status=503
                )
            protocol_config = self._model_protocol_config(model)
            self._validate_mode_capability(
                model,
                protocol_config,
                normalized_mode,
                input_count=len(references),
            )
            selected_size, output_options = self._normalize_output(model, size=size, output=output)
            policy = self.settings_service.get_image_generation_policy()
            normalized_key = self._normalize_idempotency_key(idempotency_key)
            expires_at = (
                now + policy["retention_days"] * 86_400
                if policy["retention_days"] > 0
                else 0.0
            )
            record = ImageGenerationJobRecord(
                job_id=job_id,
                user_id=user_id,
                username=username,
                prompt=normalized_prompt,
                mode=normalized_mode,
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
                        "protocol_config": protocol_config,
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
                provider_dispatched_at=0.0,
                updated_at=now,
                expires_at=expires_at,
                output_options=self._serialize_protocol_config(output_options),
            )
            try:
                job, created = self.repository.create_job_with_reservation(
                    record,
                    active_limit=policy["max_active_jobs"],
                    daily_limit=policy["daily_limit"],
                    input_references=references,
                )
            except ImageGenerationRepositoryError as exc:
                raise self._repository_error(exc) from exc
        log_event(
            "image_generation_job_submitted",
            {
                "job_id": job.job_id,
                "user_id": user_id,
                "model_id": job.model_id,
                "mode": normalized_mode,
                "input_count": len(references),
                "size": job.size,
                "output": output_options,
                "points_cost": job.points_cost,
                "idempotent_replay": not created,
                "prompt_length": len(normalized_prompt),
            },
        )
        return self._job_payload(job), created

    def process_next_job(self) -> bool:
        """执行一条队列任务，成功保存输出资产后才确认积分扣费。"""

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
        provider_dispatch_recorded = False

        def mark_provider_dispatch() -> None:
            """在协议适配器真正准备发出 HTTP 请求时记录审计时点。"""

            nonlocal provider_dispatch_recorded
            if not provider_dispatch_recorded:
                self.repository.mark_provider_dispatched(
                    job.job_id, dispatched_at=time.time()
                )
                provider_dispatch_recorded = True

        try:
            provider = self.provider_factory(execution_model)
            output_options = self._job_output_options(job, execution_model)

            # 输入资产在供应商调用前加载和校验；失败任务最终统一退回预扣积分。
            input_images, mask_asset = self._load_job_input_assets(job)
            generated = provider.generate(
                ImageGenerationRequest(
                    prompt=job.prompt,
                    size=job.size,
                    request_id=job.job_id,
                    mode=job.mode,
                    input_images=input_images,
                    mask_image=mask_asset,
                    output_options=output_options,
                    on_provider_dispatch=mark_provider_dispatch,
                )
            )
            # 内部协议适配器都会在真实 HTTP 调用前通知。若将来引入第三方适配器，
            # 成功返回本身也足以证明已产生上游调用，此处补齐审计时点。
            mark_provider_dispatch()
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
        except ImageGenerationError as exc:
            if stored_key:
                delete_generated_image(stored_key)
            self._finish_failure(
                job,
                status="failed",
                code=exc.code,
                message=exc.message,
                elapsed_ms=(time.monotonic() - started) * 1000,
                model=execution_model,
            )
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
        except Exception as exc:
            if stored_key:
                delete_generated_image(stored_key)
            # 记录详细的未知错误信息
            log_event(
                "image_generation_unexpected_error",
                {
                    "job_id": job.job_id,
                    "model_id": job.model_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            self._finish_failure(
                job,
                status="failed",
                code="IMAGE_GENERATION_FAILED",
                message=f"生图服务执行失败: {type(exc).__name__}",
                elapsed_ms=(time.monotonic() - started) * 1000,
                model=execution_model,
                trace_error=f"生图服务发生未预期错误: {str(exc)}",
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
        """启动时结算异常退出遗留的运行任务，避免积分或状态永久冻结。"""

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
                message="服务重启前的生图任务未完成，预扣积分已退回",
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

    def _load_job_input_assets(
        self, job: ImageGenerationJobRecord
    ) -> tuple[tuple[ImageInputAsset, ...], ImageInputAsset | None]:
        """从受控私有文件读取任务输入，不接受 URL、Base64 或浏览器路径。"""

        references = self.repository.list_job_inputs(job.job_id)
        source_assets: list[ImageInputAsset] = []
        mask_asset: ImageInputAsset | None = None
        primary_dimensions: tuple[int, int] | None = None
        for reference in references:
            path = (
                generation_input_image_path(reference.storage_key)
                if reference.source_kind == "uploaded"
                else generated_image_path(reference.storage_key)
            )
            if path is None or not path.is_file():
                raise ImageGenerationError(
                    "IMAGE_INPUT_UNREADABLE", "参考图片已不可用，未向生图服务发送请求"
                )
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise ImageGenerationError(
                    "IMAGE_INPUT_UNREADABLE", "参考图片读取失败，未向生图服务发送请求"
                ) from exc
            asset = ImageInputAsset(
                content=content,
                mime_type=reference.mime_type,
                role=reference.role,
            )
            if reference.role == "mask":
                mask_asset = asset
                continue
            if reference.role == "source":
                primary_dimensions = (reference.width, reference.height)
            source_assets.append(asset)
        if job.mode == "masked_edit":
            if mask_asset is None or primary_dimensions is None:
                raise ImageGenerationError(
                    "INVALID_IMAGE_INPUT", "局部编辑任务缺少主图或蒙版"
                )
            mask_reference = next(
                (
                    item
                    for item in references
                    if item.role == "mask"
                ),
                None,
            )
            if mask_reference is None or (mask_reference.width, mask_reference.height) != primary_dimensions:
                raise ImageGenerationError(
                    "INVALID_MASK_IMAGE", "蒙版尺寸必须与主图完全一致"
                )
        return tuple(source_assets), mask_asset

    def get_capabilities(self, *, user_points: int) -> dict:
        """返回用户页面初始化所需的可用模型、限额和余额。"""

        with self.lock:
            try:
                model = self.repository.get_active_model()
                policy = self.settings_service.get_image_generation_policy()
                protocol_config = self._model_protocol_config(model) if model else {}
                verified_operations = (
                    self.repository.passed_capability_operations(
                        model_id=model.model_id,
                        configuration_stamp=self._configuration_stamp(model),
                    )
                    if model
                    else set()
                )
                return {
                    "available": model is not None,
                    "model_name": model.name if model else "",
                    "provider": model.provider if model else "",
                    "sizes": self._compatibility_sizes(model, protocol_config) if model else [],
                    "output": (
                        public_output_capabilities(model.provider, protocol_config)
                        if model
                        else {"kind": "unavailable"}
                    ),
                    "input": (
                        public_input_capabilities(
                            model.provider,
                            protocol_config,
                            verified_operations=verified_operations,
                        )
                        if model
                        else {
                            "available_modes": [],
                            "verified_operations": [],
                            "max_input_images": 0,
                            "mask_mode": "none",
                            "requires_capability_test": False,
                        }
                    ),
                    "points_per_image": policy["points"],
                    "max_active_jobs": policy["max_active_jobs"],
                    "daily_limit": policy["daily_limit"],
                    "retention_days": policy["retention_days"],
                    "balance": max(0, int(user_points)),
                }
            except ImageGenerationProtocolError as exc:
                # 协议配置错误应该明确告知，而不是返回500
                raise ImageGenerationError(
                    "PROTOCOL_CONFIG_ERROR",
                    f"生图模型协议配置错误: {str(exc)}",
                    http_status=500,
                ) from exc
            except Exception as exc:
                # 捕获所有其他异常，提供详细错误信息
                log_event(
                    "image_generation_capabilities_error",
                    {
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "has_active_model": model is not None if 'model' in locals() else None,
                    },
                )
                raise ImageGenerationError(
                    "CAPABILITIES_RETRIEVAL_FAILED",
                    f"获取生图能力信息失败: {type(exc).__name__}: {str(exc)}",
                    http_status=500,
                ) from exc

    def create_input_asset(
        self, *, user_id: str, content: bytes, kind: str = "source"
    ) -> dict:
        """保存用户上传的参考图或蒙版，不将图片字节存入数据库。"""

        normalized_kind = str(kind or "source").strip().lower()
        if normalized_kind not in {"source", "mask"}:
            raise ImageGenerationError("INVALID_INPUT", "上传图片类型仅支持 source 或 mask")
        input_id = secrets.token_hex(16)
        try:
            stored = store_generation_input_image(
                input_id=input_id, content=content, kind=normalized_kind
            )
        except Exception as exc:
            message = str(exc) or "上传图片无法保存"
            raise ImageGenerationError("INVALID_IMAGE_INPUT", message) from exc
        record = ImageGenerationInputAssetRecord(
            input_id=input_id,
            user_id=user_id,
            kind=normalized_kind,
            storage_key=stored.storage_key,
            content_hash=stored.content_hash,
            mime_type=stored.mime_type,
            width=stored.width,
            height=stored.height,
            byte_size=stored.byte_size,
            created_at=time.time(),
        )
        try:
            with self.lock:
                self.repository.save_input_asset(record)
        except Exception as exc:
            delete_generation_input_image(stored.storage_key)
            raise ImageGenerationError("IMAGE_INPUT_SAVE_FAILED", "上传图片元数据保存失败") from exc
        log_event(
            "image_generation_input_uploaded",
            {
                "input_id": record.input_id,
                "user_id": user_id,
                "kind": record.kind,
                "width": record.width,
                "height": record.height,
                "byte_size": record.byte_size,
            },
        )
        return record.to_dict()

    def list_input_assets(
        self, *, user_id: str, page: int = 1, limit: int = 60
    ) -> dict:
        """列出用户可复用的上传图片与蒙版元数据。"""

        safe_page = max(1, int(page))
        safe_limit = max(1, min(int(limit), 100))
        records = self.repository.list_input_assets(
            user_id=user_id,
            offset=(safe_page - 1) * safe_limit,
            limit=safe_limit,
        )
        return {
            "assets": [item.to_dict() for item in records],
            "total": self.repository.count_input_assets(user_id=user_id),
            "page": safe_page,
            "limit": safe_limit,
        }

    def input_asset_path(self, input_id: str, *, user_id: str, allow_admin: bool) -> tuple[dict, str]:
        """返回已鉴权上传图片的安全文件路径。"""

        record = self.repository.get_input_asset(input_id)
        if record is None:
            raise ImageGenerationError("IMAGE_INPUT_NOT_FOUND", "参考图片不存在", http_status=404)
        if not allow_admin and record.user_id != user_id:
            raise ImageGenerationError("IMAGE_INPUT_FORBIDDEN", "无权访问该参考图片", http_status=403)
        path = generation_input_image_path(record.storage_key)
        if path is None or not path.is_file():
            raise ImageGenerationError("IMAGE_INPUT_NOT_FOUND", "参考图片文件不存在", http_status=404)
        return record.to_dict(), str(path)

    def delete_input_asset(self, input_id: str, *, user_id: str, allow_admin: bool) -> dict:
        """删除用户上传的私有输入图；活动任务仍引用时拒绝删除。"""

        record = self.repository.get_input_asset(input_id)
        if record is None:
            raise ImageGenerationError("IMAGE_INPUT_NOT_FOUND", "参考图片不存在", http_status=404)
        if not allow_admin and record.user_id != user_id:
            raise ImageGenerationError("IMAGE_INPUT_FORBIDDEN", "无权删除该参考图片", http_status=403)
        try:
            deleted = self.repository.delete_input_asset(
                input_id,
                user_id=record.user_id,
                now=time.time(),
            )
        except ImageGenerationRepositoryError as exc:
            raise self._repository_error(exc) from exc
        delete_generation_input_image(deleted.storage_key)
        return deleted.to_dict()

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

    def test_model(self, model_id: str, *, operation: str = "text_to_image") -> dict:
        """执行显式模型能力测试；编辑能力仅在成功测试后向用户开放。"""

        model = self.repository.get_model(model_id)
        if model is None:
            raise ImageGenerationError("IMAGE_MODEL_NOT_FOUND", "生图模型不存在", http_status=404)
        normalized_operation = self._normalize_test_operation(operation)
        protocol_config = self._model_protocol_config(model)
        if not operation_supported_by_protocol(
            model.provider, protocol_config, normalized_operation
        ):
            raise ImageGenerationError(
                "IMAGE_EDIT_UNSUPPORTED", "当前协议未声明该图片编辑能力", http_status=400
            )
        started = time.monotonic()
        input_images, mask_image = self._capability_probe_inputs(normalized_operation)
        result: dict
        try:
            selected_size, output_options = self._normalize_output(model, size="", output=None)
            provider = self.provider_factory(model)
            provider_result = provider.generate(
                ImageGenerationRequest(
                    prompt=self._capability_probe_prompt(normalized_operation),
                    size=selected_size,
                    request_id=f"test-{model_id}",
                    mode=(
                        "image_edit"
                        if normalized_operation == "whole_edit"
                        else normalized_operation
                    ),
                    input_images=input_images,
                    mask_image=mask_image,
                    output_options=output_options,
                )
            )
            validate_private_image(provider_result.content, subject="生图模型测试结果")
            result = {
                "ok": True,
                "operation": normalized_operation,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "provider_request_id": provider_result.provider_request_id,
            }
        except ImageGenerationProviderError as exc:
            result = {
                "ok": False,
                "operation": normalized_operation,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "error_code": exc.code,
                "error": exc.message,
            }
        except (ImageGenerationError, PrivateImageError) as exc:
            result = {
                "ok": False,
                "operation": normalized_operation,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "error_code": (
                    exc.code if isinstance(exc, ImageGenerationError) else "INVALID_GENERATED_IMAGE"
                ),
                "error": (
                    exc.message if isinstance(exc, ImageGenerationError) else "生图模型未返回有效图片"
                ),
            }
        except Exception:
            result = {
                "ok": False,
                "operation": normalized_operation,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "error_code": "IMAGE_GENERATION_FAILED",
                "error": "生图模型测试失败",
            }
        self.repository.save_capability_check(
            ImageGenerationCapabilityCheckRecord(
                check_id=secrets.token_hex(12),
                model_id=model.model_id,
                configuration_stamp=self._configuration_stamp(model),
                operation=normalized_operation,
                passed=bool(result["ok"]),
                error_code=str(result.get("error_code") or ""),
                error=str(result.get("error") or ""),
                checked_at=time.time(),
            )
        )
        return result

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
        """写入失败追溯，并原子退回尚未成功确认的预扣积分。"""

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
            provider = self._validate_provider(snapshot.get("provider"))
            protocol_config = self._normalize_protocol_config(
                provider,
                snapshot.get("protocol_config"),
                legacy_capabilities=snapshot.get("capabilities"),
            )
            return ImageGenerationModelRecord(
                model_id=current_model.model_id,
                name=job.model_name or current_model.name,
                provider=provider,
                base_url=self._validate_base_url(snapshot.get("base_url")),
                model=self._validate_model_identifier(snapshot.get("model")),
                api_key=api_key,
                timeout_seconds=self._validate_timeout(snapshot.get("timeout_seconds", 60.0)),
                status=current_model.status,
                capabilities=self._serialize_capabilities(
                    provider,
                    protocol_config,
                    legacy_capabilities=snapshot.get("capabilities"),
                ),
                created_at=current_model.created_at,
                updated_at=current_model.updated_at,
                protocol_config=self._serialize_protocol_config(protocol_config),
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
    def _normalize_mode(value: object) -> str:
        """将外部模式收敛为四个稳定的用户任务类型。"""

        mode = str(value or "text_to_image").strip().lower()
        allowed = {"text_to_image", *IMAGE_EDIT_MODES}
        if mode not in allowed:
            raise ImageGenerationError("INVALID_INPUT", "不支持的生图模式")
        return mode

    @staticmethod
    def _normalize_input_references(
        *,
        job_id: str,
        raw_references: object,
        mode: str,
        created_at: float,
    ) -> list[ImageGenerationJobInputRecord]:
        """验证任务只引用已保存私有资产，拒绝 URL、Base64 和浏览器文件路径。"""

        if not isinstance(raw_references, (list, tuple)):
            raise ImageGenerationError("INVALID_INPUT", "图片输入必须是资产引用数组")

        normalized: list[ImageGenerationJobInputRecord] = []
        positions: dict[str, int] = {"source": 0, "reference": 0, "mask": 0}
        allowed_keys = {"source_kind", "source_id", "source_job_id", "role"}
        for item in raw_references:
            if not isinstance(item, Mapping):
                raise ImageGenerationError("INVALID_INPUT", "图片输入必须使用资产引用对象")
            unknown = set(item) - allowed_keys
            if unknown:
                raise ImageGenerationError("INVALID_INPUT", "图片输入包含不支持的内容字段")
            source_kind = str(item.get("source_kind") or "").strip().lower()
            source_id = str(item.get("source_id") or "").strip()
            source_job_id = str(item.get("source_job_id") or "").strip()
            role = str(item.get("role") or "").strip().lower()
            if source_kind not in {"uploaded", "generated"}:
                raise ImageGenerationError("INVALID_INPUT", "图片来源类型无效")
            if role not in {"source", "reference", "mask"}:
                raise ImageGenerationError("INVALID_INPUT", "图片输入角色无效")
            if not source_id or len(source_id) > 128 or len(source_job_id) > 128:
                raise ImageGenerationError("INVALID_INPUT", "图片资产标识无效")
            if role == "mask" and source_kind != "uploaded":
                raise ImageGenerationError("INVALID_INPUT", "蒙版只能使用私有上传图片")
            if source_kind == "generated" and not source_job_id:
                raise ImageGenerationError("INVALID_INPUT", "历史生成图片必须提供来源任务标识")
            if source_kind == "uploaded" and source_job_id:
                raise ImageGenerationError("INVALID_INPUT", "上传图片不能关联来源任务")
            position = positions[role]
            positions[role] += 1
            normalized.append(
                ImageGenerationJobInputRecord(
                    job_id=job_id,
                    source_kind=source_kind,
                    source_id=source_id,
                    source_job_id=source_job_id,
                    role=role,
                    position=position,
                    mime_type="",
                    width=0,
                    height=0,
                    byte_size=0,
                    storage_key="",
                    created_at=created_at,
                )
            )

        role_counts = {role: positions[role] for role in positions}
        if mode == "text_to_image":
            valid = not normalized
        elif mode == "image_edit":
            valid = role_counts == {"source": 1, "reference": 0, "mask": 0}
        elif mode == "masked_edit":
            valid = role_counts == {"source": 1, "reference": 0, "mask": 1}
        else:  # multi_reference
            valid = (
                role_counts["source"] == 1
                and 1 <= role_counts["reference"] <= 3
                and role_counts["mask"] == 0
            )
        if not valid:
            message = {
                "text_to_image": "文生图不能携带参考图片",
                "image_edit": "整图编辑需要且只能包含一张主图",
                "masked_edit": "局部编辑需要一张主图和一张同尺寸蒙版",
                "multi_reference": "多图参考需要一张主图和一到三张参考图",
            }[mode]
            raise ImageGenerationError("INVALID_IMAGE_INPUT", message)
        return normalized

    def _validate_mode_capability(
        self,
        model: ImageGenerationModelRecord,
        protocol_config: Mapping[str, Any],
        mode: str,
        *,
        input_count: int,
    ) -> None:
        """仅允许通过当前模型配置实测的编辑能力进入供应商调用链路。"""

        if mode == "text_to_image":
            return
        capability = MODE_TO_CAPABILITY[mode]
        if not operation_supported_by_protocol(model.provider, protocol_config, capability):
            raise ImageGenerationError("IMAGE_EDIT_UNSUPPORTED", "当前生图协议不支持该图片编辑模式")
        max_inputs = int(
            (protocol_config.get("input_capabilities") or {}).get("max_input_images") or 0
        )
        if input_count > max_inputs:
            raise ImageGenerationError("INVALID_IMAGE_INPUT", "图片输入数量超过当前模型允许范围")
        passed = self.repository.passed_capability_operations(
            model_id=model.model_id,
            configuration_stamp=self._configuration_stamp(model),
        )
        if capability not in passed:
            raise ImageGenerationError(
                "IMAGE_EDIT_NOT_VERIFIED",
                "当前模型尚未通过此图片编辑能力测试",
                http_status=409,
            )

    @staticmethod
    def _normalize_test_operation(value: object) -> str:
        """规范管理员能力测试操作；兼容 ``image_edit`` 作为整图编辑别名。"""

        operation = str(value or "text_to_image").strip().lower()
        aliases = {"image_edit": "whole_edit"}
        operation = aliases.get(operation, operation)
        allowed = {"text_to_image", *MODE_TO_CAPABILITY.values()}
        if operation not in allowed:
            raise ImageGenerationError("INVALID_INPUT", "不支持的模型能力测试类型")
        return operation

    @staticmethod
    def _capability_probe_inputs(
        operation: str,
    ) -> tuple[tuple[ImageInputAsset, ...], ImageInputAsset | None]:
        """构建只在内存使用的最小测试图片，绝不落盘或写入任务记录。"""

        if operation == "text_to_image":
            return (), None

        source = Image.new("RGB", (32, 32), "#2563eb")
        source_bytes = io.BytesIO()
        source.save(source_bytes, format="PNG")
        source_asset = ImageInputAsset(
            content=source_bytes.getvalue(), mime_type="image/png", role="source"
        )
        if operation == "whole_edit":
            return (source_asset,), None
        if operation == "masked_edit":
            mask = Image.new("L", (32, 32), 0)
            for x in range(16, 32):
                for y in range(32):
                    mask.putpixel((x, y), 255)
            mask_bytes = io.BytesIO()
            mask.save(mask_bytes, format="PNG")
            return (
                (source_asset,),
                ImageInputAsset(
                    content=mask_bytes.getvalue(), mime_type="image/png", role="mask"
                ),
            )
        if operation == "multi_reference":
            reference = Image.new("RGB", (32, 32), "#f97316")
            reference_bytes = io.BytesIO()
            reference.save(reference_bytes, format="PNG")
            return (
                (
                    source_asset,
                    ImageInputAsset(
                        content=reference_bytes.getvalue(),
                        mime_type="image/png",
                        role="reference",
                    ),
                ),
                None,
            )
        raise ImageGenerationError("INVALID_INPUT", "不支持的模型能力测试类型")

    @staticmethod
    def _capability_probe_prompt(operation: str) -> str:
        """给各能力测试提供最小且与操作匹配的测试指令。"""

        prompts = {
            "text_to_image": "Generate a small blue geometric square on a plain white background.",
            "whole_edit": "Change the blue square in the input image to a red circle.",
            "masked_edit": "Only change the white-mask area to orange. Preserve the black-mask area exactly.",
            "multi_reference": "Use the main image composition and apply the reference image color style.",
        }
        return prompts[operation]

    @staticmethod
    def _configuration_stamp(model: ImageGenerationModelRecord) -> str:
        """生成不含密钥的模型配置指纹，配置变化会自然使旧能力测试失效。"""

        payload = {
            "provider": model.provider,
            "base_url": model.base_url,
            "model": model.model,
            "timeout_seconds": model.timeout_seconds,
            "protocol_config": model.protocol_config,
            "updated_at": model.updated_at,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
                "生图提供商不受支持",
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

    @staticmethod
    def _serialize_protocol_config(value: Mapping[str, object]) -> str:
        """稳定保存已校验的协议或输出配置。"""

        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _normalize_protocol_config(
        self,
        provider: str,
        value: object,
        *,
        legacy_capabilities: object = None,
    ) -> dict[str, Any]:
        """将协议配置限制在已支持的字段与能力范围内。"""

        try:
            return normalize_protocol_config(
                provider,
                value,
                legacy_capabilities=legacy_capabilities,
            )
        except ImageGenerationProtocolError as exc:
            raise ImageGenerationError("INVALID_INPUT", str(exc)) from exc

    def _model_protocol_config(self, model: ImageGenerationModelRecord) -> dict[str, Any]:
        """读取模型的结构化协议配置，并兼容旧能力字段。"""

        return self._normalize_protocol_config(
            model.provider,
            model.protocol_config,
            legacy_capabilities=model.capabilities,
        )

    @staticmethod
    def _serialize_capabilities(
        provider: str,
        protocol_config: dict[str, Any],
        *,
        legacy_capabilities: object = None,
    ) -> str:
        """生成兼容旧客户端的平铺能力字段。"""

        return ",".join(
            capabilities_for_protocol(
                provider,
                protocol_config,
                legacy_capabilities=legacy_capabilities,
            )
        )

    def _normalize_output(
        self,
        model: ImageGenerationModelRecord,
        *,
        size: object,
        output: object,
    ) -> tuple[str, dict[str, str]]:
        """将外部输入统一成可复现、与当前协议匹配的输出参数。"""

        try:
            return normalize_output_options(
                model.provider,
                self._model_protocol_config(model),
                size=size,
                output=output,
            )
        except ImageGenerationProtocolError as exc:
            raise ImageGenerationError("INVALID_INPUT", str(exc)) from exc

    def _compatibility_sizes(
        self,
        model: ImageGenerationModelRecord,
        protocol_config: dict[str, Any],
    ) -> list[str]:
        """继续返回旧字段 ``sizes``，新前端改用结构化 ``output``。"""

        if model.provider in {OPENAI_IMAGES_PROVIDER, OPENAI_COMPATIBLE_IMAGES_PROVIDER}:
            return list(protocol_config["preset_sizes"])
        if model.provider == LEGACY_OPENAI_CHAT_IMAGE_PROVIDER:
            return [
                capability
                for capability in self._capabilities(model)
                if "x" in capability
            ]
        return []

    def _job_output_options(
        self,
        job: ImageGenerationJobRecord,
        model: ImageGenerationModelRecord,
    ) -> dict[str, str]:
        """恢复提交时输出参数，兼容还未保存该字段的历史任务。"""

        if model.provider == LEGACY_OPENAI_CHAT_IMAGE_PROVIDER:
            return {"mode": "model-controlled"}
        try:
            output = json.loads(job.output_options or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ImageGenerationError("MODEL_SNAPSHOT_INVALID", "生图任务输出参数无效") from exc
        if output and not isinstance(output, dict):
            raise ImageGenerationError("MODEL_SNAPSHOT_INVALID", "生图任务输出参数无效")
        try:
            _, normalized = self._normalize_output(
                model,
                size="" if output else job.size,
                output=output or None,
            )
            return normalized
        except ImageGenerationError as exc:
            raise ImageGenerationError("MODEL_SNAPSHOT_INVALID", "生图任务输出参数无效") from exc

    @staticmethod
    def _repository_error(exc: ImageGenerationRepositoryError) -> ImageGenerationError:
        return ImageGenerationError(exc.code, exc.message, http_status=exc.http_status)
