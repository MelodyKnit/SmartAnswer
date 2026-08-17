"""文本生图任务、私有资产与模型管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile
from starlette.responses import FileResponse, JSONResponse, Response

from ....media.image_assets import MAX_PRIVATE_IMAGE_BYTES
from ....platform.image_generation.service import ImageGenerationError
from ....llm.image_generation.size_inference import (
    infer_gemini_output,
    infer_openai_size,
    explain_size_choice,
)
from ...dependencies import ImageGenerationServiceDep
from ...security import (
    current_user,
    forbidden_response,
    require_permissions,
    unauthorized_response,
)
from .schemas import (
    ImageGenerationCreatePayload,
    ImageGenerationModelTestPayload,
    ImageGenerationModelCreatePayload,
    ImageGenerationModelUpdatePayload,
    ImageSizeInferencePayload,
)


def build_image_generation_router() -> APIRouter:
    """构建独立的生图、修图、私有输入资产与模型管理 API。"""

    router = APIRouter(tags=["image-generation"])

    @router.get("/image-generation-capabilities")
    def image_generation_capabilities(
        request: Request, service: ImageGenerationServiceDep
    ) -> JSONResponse:
        """返回当前登录用户的可用模型、额度和余额。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        try:
            capabilities = service.get_capabilities(
                user_points=int(user.get("points") or 0)
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse(
            {
                "ok": True,
                "capabilities": capabilities,
            }
        )

    @router.post("/image-generation-infer-size")
    def image_generation_infer_size(
        request: Request,
        payload: ImageSizeInferencePayload,
        service: ImageGenerationServiceDep,
    ) -> JSONResponse:
        """根据用户描述智能推断最合适的图片尺寸和画幅比例。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user

        try:
            capabilities = service.get_capabilities(user_points=int(user.get("points") or 0))
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        output_config = capabilities.get("output", {})
        output_kind = output_config.get("kind", "unavailable")

        if output_kind == "gemini":
            available_ratios = output_config.get("aspect_ratios", ["1:1"])
            available_sizes = output_config.get("image_sizes", ["1K"])
            inferred = infer_gemini_output(payload.prompt, available_ratios, available_sizes)
            explanation = explain_size_choice(
                payload.prompt,
                inferred["aspect_ratio"],
                inferred["image_size"]
            )
            return JSONResponse({
                "ok": True,
                "output": inferred,
                "explanation": explanation,
            })
        elif output_kind in {"openai-images", "compatible-images"}:
            available_sizes = output_config.get("preset_sizes", ["1024x1024"])
            inferred_size = infer_openai_size(payload.prompt, available_sizes)
            explanation = explain_size_choice(payload.prompt, "auto", inferred_size)
            return JSONResponse({
                "ok": True,
                "output": {"size": inferred_size},
                "explanation": explanation,
            })
        else:
            return JSONResponse({
                "ok": True,
                "output": {},
                "explanation": "当前模型由提供商自动决定尺寸",
            })

    @router.post("/image-generations")
    def image_generation_create(
        request: Request,
        payload: ImageGenerationCreatePayload,
        service: ImageGenerationServiceDep,
    ) -> JSONResponse:
        """创建一条异步生图任务，并同步完成积分预扣。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            idempotency_key = payload.idempotency_key
        try:
            job, created = service.create_job(
                user_id=str(user["user_id"]),
                username=str(user["username"]),
                prompt=payload.prompt,
                size=payload.size,
                mode=payload.mode,
                input_assets=[item.model_dump() for item in payload.input_assets],
                output=payload.output,
                idempotency_key=idempotency_key,
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse(
            {"ok": True, "job": job, "idempotent_replay": not created},
            status_code=202 if created else 200,
        )

    @router.post("/image-generation-inputs")
    async def image_generation_input_upload(
        request: Request,
        service: ImageGenerationServiceDep,
        image: UploadFile = File(...),
        kind: str = "source",
    ) -> JSONResponse:
        """上传私有参考图或蒙版；任务创建时只引用返回的资产 ID。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        content = await image.read(MAX_PRIVATE_IMAGE_BYTES + 1)
        try:
            asset = service.create_input_asset(
                user_id=str(user["user_id"]), content=content, kind=kind
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        finally:
            await image.close()
        return JSONResponse({"ok": True, "asset": asset}, status_code=201)

    @router.get("/image-generation-inputs")
    def image_generation_inputs_list(
        request: Request,
        service: ImageGenerationServiceDep,
        page: int = 1,
        limit: int = 60,
    ) -> JSONResponse:
        """列出当前用户仍可作为编辑输入的私有上传图片。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        return JSONResponse(
            {
                "ok": True,
                **service.list_input_assets(
                    user_id=str(user["user_id"]), page=page, limit=limit
                ),
            }
        )

    @router.get("/image-generation-inputs/{input_id}/content")
    def image_generation_input_content(
        request: Request,
        input_id: str,
        service: ImageGenerationServiceDep,
    ) -> Response:
        """按所有者权限返回私有上传图，不提供可猜测的公开链接。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        try:
            asset, path = service.input_asset_path(
                input_id,
                user_id=str(user["user_id"]),
                allow_admin=has_permission(user, "llm:read"),
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        response = FileResponse(path, media_type=str(asset["mime_type"]))
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @router.delete("/image-generation-inputs/{input_id}")
    def image_generation_input_delete(
        request: Request,
        input_id: str,
        service: ImageGenerationServiceDep,
    ) -> JSONResponse:
        """删除未被活动任务使用的私有上传图。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        try:
            asset = service.delete_input_asset(
                input_id,
                user_id=str(user["user_id"]),
                allow_admin=has_permission(user, "llm:read"),
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse({"ok": True, "asset": asset})

    @router.get("/image-generations")
    def image_generation_list(
        request: Request,
        service: ImageGenerationServiceDep,
        status: str = "",
        page: int = 1,
        limit: int = 30,
        user_id: str = "",
    ) -> JSONResponse:
        """列出个人任务；管理员可按用户审计任务。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        can_manage = has_permission(user, "llm:read")
        if user_id and not can_manage:
            return forbidden_response("无权查看其他用户的生图任务")
        try:
            result = service.list_jobs(
                user_id=user_id.strip() if can_manage and user_id.strip() else str(user["user_id"]),
                status=status.strip(),
                page=page,
                limit=limit,
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse({"ok": True, **result})

    @router.get("/image-generations/{job_id}")
    def image_generation_detail(
        request: Request, job_id: str, service: ImageGenerationServiceDep
    ) -> JSONResponse:
        """读取单条任务及其仍可访问的资产描述。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        try:
            job = service.ensure_job_owner(
                job_id,
                user_id=str(user["user_id"]),
                allow_admin=has_permission(user, "llm:read"),
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse({"ok": True, "job": job})

    @router.get("/image-generations/{job_id}/assets/{asset_id}/content")
    def image_generation_asset_content(
        request: Request,
        job_id: str,
        asset_id: str,
        service: ImageGenerationServiceDep,
    ) -> Response:
        """以登录用户权限返回私有生成图片，拒绝公开直链访问。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        try:
            service.ensure_job_owner(
                job_id,
                user_id=str(user["user_id"]),
                allow_admin=has_permission(user, "llm:read"),
            )
            asset, path = service.asset_path(job_id, asset_id)
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        response = FileResponse(path, media_type=str(asset["mime_type"]))
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @router.delete("/image-generations/{job_id}")
    def image_generation_delete(
        request: Request, job_id: str, service: ImageGenerationServiceDep
    ) -> JSONResponse:
        """取消排队任务或删除已结束任务及其私有资产。"""

        user = require_image_generation_user(request)
        if isinstance(user, JSONResponse):
            return user
        try:
            job = service.delete_or_cancel_job(
                job_id,
                user_id=str(user["user_id"]),
                allow_admin=has_permission(user, "llm:read"),
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse({"ok": True, "job": job})

    @router.get("/image-generation-models")
    def image_generation_models_list(
        request: Request, service: ImageGenerationServiceDep
    ) -> JSONResponse:
        """读取管理员可见的生图模型配置，密钥始终掩码。"""

        denied = require_image_generation_management_read(request)
        if denied:
            return denied
        return JSONResponse({"ok": True, "models": service.list_models()})

    @router.post("/image-generation-models")
    def image_generation_model_create(
        request: Request,
        payload: ImageGenerationModelCreatePayload,
        service: ImageGenerationServiceDep,
    ) -> JSONResponse:
        """创建独立的生图模型配置。"""

        denied = require_image_generation_management_write(request)
        if denied:
            return denied
        try:
            model = service.create_model(**payload.model_dump())
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse({"ok": True, "model": model}, status_code=201)

    @router.patch("/image-generation-models/{model_id}")
    def image_generation_model_update(
        request: Request,
        model_id: str,
        payload: ImageGenerationModelUpdatePayload,
        service: ImageGenerationServiceDep,
    ) -> JSONResponse:
        """更新独立的生图模型配置。"""

        denied = require_image_generation_management_write(request)
        if denied:
            return denied
        values = {key: value for key, value in payload.model_dump().items() if value is not None}
        try:
            model = service.update_model(model_id, values)
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        return JSONResponse({"ok": True, "model": model})

    @router.delete("/image-generation-models/{model_id}")
    def image_generation_model_delete(
        request: Request, model_id: str, service: ImageGenerationServiceDep
    ) -> JSONResponse:
        """删除无活动任务引用的生图模型。"""

        denied = require_image_generation_management_write(request)
        if denied:
            return denied
        try:
            deleted = service.delete_model(model_id)
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)
        if not deleted:
            return image_generation_error_response(
                ImageGenerationError("IMAGE_MODEL_NOT_FOUND", "生图模型不存在", http_status=404)
            )
        return JSONResponse({"ok": True})

    @router.post("/image-generation-models/{model_id}/test")
    def image_generation_model_test(
        request: Request,
        model_id: str,
        service: ImageGenerationServiceDep,
        payload: ImageGenerationModelTestPayload | None = None,
    ) -> JSONResponse:
        """执行管理员明确触发的生图连通性测试，不保留图片。"""

        denied = require_image_generation_management_write(request)
        if denied:
            return denied
        try:
            return JSONResponse(
                service.test_model(
                    model_id,
                    operation=payload.operation if payload is not None else "text_to_image",
                )
            )
        except ImageGenerationError as exc:
            return image_generation_error_response(exc)

    @router.get("/image-generation-stats")
    def image_generation_stats(
        request: Request, service: ImageGenerationServiceDep
    ) -> JSONResponse:
        """返回生图任务和调用耗时统计。"""

        denied = require_image_generation_management_read(request)
        if denied:
            return denied
        return JSONResponse({"ok": True, "stats": service.stats()})

    @router.get("/image-generation-traces")
    def image_generation_traces(
        request: Request,
        service: ImageGenerationServiceDep,
        job_id: str = "",
        model_id: str = "",
        page: int = 1,
        limit: int = 100,
    ) -> JSONResponse:
        """查询不含提示词和密钥的供应商调用追溯。"""

        denied = require_image_generation_management_read(request)
        if denied:
            return denied
        return JSONResponse(
            {
                "ok": True,
                **service.list_traces(
                    job_id=job_id,
                    model_id=model_id,
                    page=page,
                    limit=limit,
                ),
            }
        )

    return router


def require_image_generation_user(request: Request) -> dict | JSONResponse:
    """统一校验登录态与生图使用权限。"""

    user = current_user(request)
    if user is None:
        return unauthorized_response("请先登录")
    denied = require_permissions(request, {"image-generation:use"})
    return denied or user


def has_permission(user: dict, permission: str) -> bool:
    """判断当前用户是否拥有用于跨用户审计的管理权限。"""

    return str(user.get("role")) == "superadmin" or permission in set(
        user.get("permissions") or ()
    )


def require_image_generation_management_read(request: Request) -> JSONResponse | None:
    """校验生图管理读取权限。"""

    return require_permissions(request, {"llm:read"})


def require_image_generation_management_write(request: Request) -> JSONResponse | None:
    """校验生图管理写入权限。"""

    return require_permissions(request, {"llm:write"})


def image_generation_error_response(exc: ImageGenerationError) -> JSONResponse:
    """将生图领域错误转换为统一 API 响应。"""

    # 这些错误来自配置解析或基础设施访问，异常文本可能包含数据库、路径或
    # 上游实现细节。其余领域错误继续保留 service 提供的用户可执行文案。
    internal_messages = {
        "CAPABILITIES_RETRIEVAL_FAILED": "暂时无法读取生图能力，请稍后重试",
        "PROTOCOL_CONFIG_ERROR": "生图模型配置无效，请联系管理员检查模型配置",
    }
    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": internal_messages.get(exc.code, exc.message),
            },
        },
        status_code=exc.http_status,
    )
