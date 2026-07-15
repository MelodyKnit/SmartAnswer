"""测试品牌 Logo 上传、裁剪缩放及访问路由逻辑。"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from study_qb_assistant.api.app import create_app
from study_qb_assistant.config import GlobalConfig
from study_qb_assistant.media.brand_images import (
    BrandLogoError,
    process_and_save_brand_logo,
)


@pytest.fixture
def temp_brand_dir():
    """提供临时的品牌图片目录，测试完自动清理。"""
    temp_dir = Path(tempfile.mkdtemp(prefix="stqb_brand_test_"))
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def temp_db_dir():
    """提供临时的全局数据库环境。"""
    temp_dir = Path(tempfile.mkdtemp(prefix="stqb_db_test_"))
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


def test_process_and_save_brand_logo(temp_brand_dir):
    """测试图片裁剪与不同分辨率尺寸生成。"""
    # 1. 构造一个 200x100 的宽图（非正方形），并在其中绘制不同的颜色
    img = Image.new("RGBA", (200, 100), color=(255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    content_bytes = buf.getvalue()

    # 2. 调用生成方法
    urls = process_and_save_brand_logo(content_bytes, temp_brand_dir)

    # 3. 验证是否生成了 4 个级别的图片
    assert "original" in urls
    assert "lg" in urls
    assert "md" in urls
    assert "sm" in urls

    assert urls["original"] == "/media/brand/logo_original.png"
    assert urls["lg"] == "/media/brand/logo_lg.png"
    assert urls["md"] == "/media/brand/logo_md.png"
    assert urls["sm"] == "/media/brand/logo_sm.png"

    # 4. 验证生成的物理文件的分辨率是否均为高宽相同的正方形，且尺寸符合设定
    for key, expected_size in [("original", 100), ("lg", 128), ("md", 64), ("sm", 32)]:
        path = temp_brand_dir / f"logo_{key}.png"
        assert path.is_file()
        with Image.open(path) as saved_img:
            assert saved_img.size == (expected_size, expected_size)


def test_process_and_save_brand_logo_rejects_oversized_pixel_count(
    temp_brand_dir, monkeypatch
):
    """测试像素数超过安全上限的图片会被拒绝，避免压缩炸弹拖垮进程。"""

    import study_qb_assistant.media.brand_images as brand_images

    monkeypatch.setattr(brand_images, "MAX_BRAND_LOGO_PIXELS", 10)
    img = Image.new("RGBA", (4, 4), color=(255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")

    with pytest.raises(BrandLogoError):
        process_and_save_brand_logo(buf.getvalue(), temp_brand_dir)


def test_system_logo_upload_and_download(temp_brand_dir, temp_db_dir, monkeypatch):
    """通过 TestClient 测试管理员上传及品牌图片分发路由。"""
    # 让全局 config 对象的 brand_images_dir 重定向到临时测试目录
    monkeypatch.setattr(GlobalConfig, "brand_images_dir", temp_brand_dir)

    from study_qb_assistant.auth import AuthService
    from study_qb_assistant.platform.container import PlatformServices
    from study_qb_assistant.search import LocalQuestionIndex

    db_path = temp_db_dir / "study-qb.sqlite3"
    auth = AuthService(db_path)
    platform = PlatformServices(db_path)

    # 模拟空题库索引
    index = LocalQuestionIndex(records=())

    # 创建测试应用和客户端
    app = create_app(
        index,
        auth_service=auth,
        platform_services=platform,
        require_auth=True,
    )
    client = TestClient(app)

    # 1. 注册超级管理员以获取 Token
    client.post(
        "/auth/register", json={"username": "sysadmin", "password": "securepassword"}
    )
    login_res = client.post(
        "/auth/login", json={"username": "sysadmin", "password": "securepassword"}
    )
    token = login_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 创建一个长图 100x300 进行上传测试
    input_img = Image.new("RGBA", (100, 300), color=(0, 255, 0, 255))
    buf = io.BytesIO()
    input_img.save(buf, "PNG")
    file_bytes = buf.getvalue()

    # 3. 发送上传请求
    upload_res = client.post(
        "/system/logo/upload",
        files={"file": ("logo.png", file_bytes, "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 200
    res_data = upload_res.json()
    assert res_data["ok"] is True
    assert "logo_lg.png" in res_data["urls"]["lg"]

    # 4. 请求下载获取裁剪后的媒体文件
    download_res = client.get("/media/brand/logo_lg.png")
    assert download_res.status_code == 200
    assert download_res.headers["content-type"] == "image/png"

    with Image.open(io.BytesIO(download_res.content)) as downloaded_img:
        assert downloaded_img.size == (128, 128)

    # 5. 测试目录穿越防护 (Path Traversal Protection)
    traversal_res = client.get("/media/brand/../ocs/images/somefile.png")
    assert traversal_res.status_code == 404

    traversal_res_2 = client.get("/media/brand/sub/file.png")
    assert traversal_res_2.status_code == 404


def test_system_logo_upload_rejects_invalid_image_bytes(
    temp_brand_dir, temp_db_dir, monkeypatch
):
    """测试伪装为图片的非法字节不会触发 500。"""

    monkeypatch.setattr(GlobalConfig, "brand_images_dir", temp_brand_dir)

    from study_qb_assistant.auth import AuthService
    from study_qb_assistant.platform.container import PlatformServices
    from study_qb_assistant.search import LocalQuestionIndex

    db_path = temp_db_dir / "study-qb.sqlite3"
    auth = AuthService(db_path)
    platform = PlatformServices(db_path)
    app = create_app(
        LocalQuestionIndex(records=()),
        auth_service=auth,
        platform_services=platform,
        require_auth=True,
    )
    client = TestClient(app)

    client.post(
        "/auth/register", json={"username": "sysadmin", "password": "securepassword"}
    )
    login_res = client.post(
        "/auth/login", json={"username": "sysadmin", "password": "securepassword"}
    )
    headers = {"Authorization": f"Bearer {login_res.json()['token']}"}

    upload_res = client.post(
        "/system/logo/upload",
        files={"file": ("logo.png", b"not-an-image", "image/png")},
        headers=headers,
    )

    assert upload_res.status_code == 400
    assert upload_res.json()["error"]["code"] == "INVALID_INPUT"


def test_redeem_code_custom_and_bulk(temp_db_dir):
    """测试管理员创建自定义兑换码，以及随机兑换码批量创建的后端逻辑。"""
    from study_qb_assistant.auth import AuthService
    from study_qb_assistant.platform.container import PlatformServices
    from study_qb_assistant.search import LocalQuestionIndex

    db_path = temp_db_dir / "study-qb.sqlite3"
    auth = AuthService(db_path)
    platform = PlatformServices(db_path)
    index = LocalQuestionIndex(records=())

    app = create_app(
        index, auth_service=auth, platform_services=platform, require_auth=True
    )
    client = TestClient(app)

    # 1. 注册超级管理员获取 Token
    client.post(
        "/auth/register", json={"username": "sysadmin", "password": "securepassword"}
    )
    login_res = client.post(
        "/auth/login", json={"username": "sysadmin", "password": "securepassword"}
    )
    token = login_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 测试创建单个自定义兑换码
    res = client.post(
        "/wallet/redeem-codes",
        json={
            "kind": "points",
            "points": 1000,
            "max_uses": 5,
            "code": "VIP_WELCOME_2026",
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["redeem_code"]["code"] == "VIP_WELCOME_2026"
    assert data["redeem_code"]["points"] == 1000
    assert data["redeem_code"]["max_uses"] == 5

    # 再次创建具有相同名字的自定义兑换码应该报错 (唯一性验证)
    res_dup = client.post(
        "/wallet/redeem-codes",
        json={"kind": "points", "points": 500, "code": "VIP_WELCOME_2026"},
        headers=headers,
    )
    assert res_dup.status_code == 400
    assert "已存在" in res_dup.json()["error"]["message"]

    # 3. 测试批量随机创建兑换码 (如 5 个 1000 积分兑换码)
    res_bulk = client.post(
        "/wallet/redeem-codes",
        json={"kind": "points", "points": 1000, "count": 5},
        headers=headers,
    )
    assert res_bulk.status_code == 200
    data_bulk = res_bulk.json()
    assert data_bulk["ok"] is True
    assert data_bulk["redeem_code"]["points"] == 1000

    # 获取列表验证目前数据库中新增的兑换码
    list_res = client.get("/wallet/redeem-codes", headers=headers)
    assert list_res.status_code == 200
    all_codes = list_res.json()["redeem_codes"]
    # 应该包括 (1个自定义兑换码 + 5个批量创建的兑换码) = 6个
    assert len(all_codes) == 6

    # 过滤出 1000 积分的随机兑换码 (前缀以 rc_ 开头)
    random_1000_codes = [
        c for c in all_codes if c["points"] == 1000 and c["code"].startswith("rc_")
    ]
    assert len(random_1000_codes) == 5
