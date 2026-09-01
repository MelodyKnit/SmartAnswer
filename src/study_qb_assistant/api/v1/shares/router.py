"""无状态 API Key 分享模板路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from ....adapters.ocs.config import build_ocs_config_name
from ....platform.import_scripts.templates import get_import_script_template, render_import_script
from ...dependencies import get_settings_service
from ...http import base_url_from_request


def build_share_router() -> APIRouter:
    """构建无需登录的分享模板接口。"""

    router = APIRouter()

    @router.get("/shares/apikey-template")
    def apikey_template(request: Request) -> JSONResponse:
        settings = get_settings_service(request)
        site_title = str(settings.get_site_config()["site_title"])
        template = get_import_script_template()
        rendered = render_import_script(
            template,
            base_url_from_request(request, settings),
            config_name=build_ocs_config_name(site_title, token_description="共享配置"),
        )
        return JSONResponse(
            {
                "ok": True,
                "template_id": template.template_id,
                "script": rendered["content"],
                "ocs_config": rendered["ocs_config"],
            },
            headers={"Cache-Control": "public, max-age=300"},
        )

    return router
