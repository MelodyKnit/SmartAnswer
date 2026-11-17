"""仅使用临时数据库验证模型角色界面，不可用于生产数据或远程服务器。

先构建前端，再运行：
conda run -n ai-study-qb python tests/manual/check_llm_model_roles_ui.py --output-dir .local/llm-role-qa
需要当前测试环境已安装 Playwright 及 Chromium；也可传 --browser-channel msedge 使用本机 Edge。
不会调用真实模型。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

import uvicorn
from playwright.sync_api import expect, sync_playwright

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-channel", choices=("msedge", "chrome"), default=None)
    arguments = parser.parse_args()
    output = arguments.output_dir
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stqb-model-role-ui-") as directory:
        database = Path(directory) / "ui.sqlite3"
        # 强制隔离运行库和日志，避免开发环境变量把测试指向现有数据。
        os.environ["STQB_DATABASE_URL"] = "sqlite:///" + database.as_posix()
        os.environ["STQB_DATA_DIR"] = directory
        os.environ["STQB_LOG_PATH"] = str(Path(directory) / "events.jsonl")
        platform = PlatformServices(database)
        models = {}
        for name, priority in (("Main Model", 9999), ("Backup One", 10), ("Backup Two", 20)):
            models[name] = platform.llm.create_model(
                name=name, base_url="https://models.example/v1", model=name, priority=priority,
            )
        app = create_app(
            LocalQuestionIndex(()), auth_service=AuthService(database),
            platform_services=platform, require_auth=True,
        )
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if not worker.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("临时测试服务器未启动")
                time.sleep(0.05)
            run_browser_checks(origin, platform, models, output, arguments.browser_channel)
        finally:
            server.should_exit = True
            worker.join(timeout=15)
            listener.close()


def run_browser_checks(origin, platform, models, output, browser_channel) -> None:
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=browser_channel)
        try:
            for theme in ("light", "dark"):
                for layout, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
                    platform.llm.update_model(models["Main Model"]["model_id"], {"role": "primary"})
                    context = browser.new_context(viewport={"width": width, "height": height})
                    context.request.post(origin + "/api/v1/auth/register", data={
                        "username": "uiowner", "password": "ui-test-password",
                    })
                    login = context.request.post(origin + "/api/v1/auth/login", data={
                        "username": "uiowner", "password": "ui-test-password",
                    })
                    assert login.ok, login.status
                    token = json.dumps(login.json()["token"])
                    context.add_init_script(
                        f"localStorage.setItem('stqb_token', {token});"
                        f"localStorage.setItem('stqb_theme_mode', '{theme}');"
                    )
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(origin + "/llm-models")
                    page.get_by_role("tab", name="模型配置", exact=True).click()
                    row = page.locator(".el-table__body tr").filter(has_text="Backup One")
                    row.get_by_role("button", name="编辑", exact=True).click()
                    dialog = page.get_by_role("dialog", name="编辑模型", exact=True)
                    priority_label = dialog.get_by_text("备用优先级（越小越先尝试）", exact=True)
                    expect(priority_label).to_be_visible()
                    expect(dialog).to_have_css("opacity", "1")
                    page.screenshot(
                        path=output / f"{theme}-{layout}-backup.png", full_page=True,
                        animations="disabled",
                    )
                    dialog.locator(".el-select").click()
                    page.get_by_role("option", name="主用", exact=True).click()
                    expect(page.get_by_role("option", name="主用", exact=True)).not_to_be_visible()
                    expect(priority_label).to_have_count(0)
                    expect(dialog.get_by_text("保存后，当前主用「Main Model」将自动改为备用。", exact=True)).to_be_visible()
                    assert dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
                    bounds = dialog.bounding_box()
                    assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
                    page.screenshot(
                        path=output / f"{theme}-{layout}-promote.png", full_page=True,
                        animations="disabled",
                    )
                    with page.expect_response(lambda response:
                        response.request.method == "PATCH" and "/llm-models/" in response.url
                    ) as saved:
                        dialog.get_by_role("button", name="保存", exact=True).click()
                    assert saved.value.ok
                    assert saved.value.request.post_data_json == {"role": "primary"}
                    expect(dialog).not_to_be_visible()
                    expect(row.get_by_text("主用", exact=True)).to_be_visible()
                    original = page.locator(".el-table__body tr").filter(has_text="Main Model")
                    expect(original.get_by_text("备用", exact=True)).to_be_visible()
                    assert sum(item["role"] == "primary" for item in platform.llm.list_models()) == 1
                    # 弹窗保留旧角色时，只改名称不能覆盖另一管理员刚完成的主用切换。
                    row.get_by_role("button", name="编辑", exact=True).click()
                    expect(dialog).to_be_visible()
                    platform.llm.update_model(models["Main Model"]["model_id"], {"role": "primary"})
                    dialog.get_by_placeholder("便于识别的名称").fill("Backup Renamed")
                    with page.expect_response(lambda response:
                        response.request.method == "PATCH" and "/llm-models/" in response.url
                    ) as renamed:
                        dialog.get_by_role("button", name="保存", exact=True).click()
                    assert renamed.value.ok
                    assert renamed.value.request.post_data_json == {"name": "Backup Renamed"}
                    expect(dialog).not_to_be_visible()
                    assert platform.llm.get_model(models["Backup One"]["model_id"])["role"] == "backup"
                    platform.llm.update_model(models["Backup One"]["model_id"], {"name": "Backup One"})
                    assert not errors, errors
                    results.append({
                        "theme": theme, "layout": layout,
                        "promotion": "passed", "stale_edit": "passed",
                    })
                    context.close()
        finally:
            browser.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
