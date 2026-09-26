"""无状态 API Key 分享模板路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....adapters.ocs.config import build_ocs_config
from ...dependencies import get_settings_service
from ...http import base_url_from_request


def build_share_router() -> APIRouter:
    """构建无需登录的分享模板接口。"""

    router = APIRouter()

    @router.get("/shares/apikey-template")
    def apikey_template(request: Request) -> JSONResponse:
        settings = get_settings_service(request)
        site_title = str(settings.get_site_config()["site_title"])
        ocs_config = build_ocs_config(
            base_url_from_request(request, settings),
            platform_name=site_title,
            token_description="共享配置",
        )
        return JSONResponse(
            {
                "ok": True,
                "ocs_config": ocs_config,
            },
            headers={"Cache-Control": "public, max-age=300"},
        )

    return router
