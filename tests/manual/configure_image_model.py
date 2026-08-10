#!/usr/bin/env python3
"""快速配置生图模型的自动化脚本"""

import sys
import requests
import json
import getpass
from pathlib import Path


BASE_URL = "http://127.0.0.1:8765"


def login(username: str, password: str) -> str:
    """登录并获取 token"""
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"username": username, "password": password}
    )
    if response.status_code != 200:
        raise Exception(f"登录失败: {response.text}")

    data = response.json()
    return data["token"]


def create_openai_model(token: str, api_key: str) -> dict:
    """创建 OpenAI DALL-E 3 测试模型"""
    headers = {"Authorization": f"Bearer {token}"}

    model_config = {
        "name": "OpenAI DALL-E 3 测试",
        "provider": "openai-images",
        "base_url": "https://api.openai.com/v1",
        "model": "dall-e-3",
        "api_key": api_key,
        "status": "active",
        "timeout_seconds": 120,
        "protocol_config": {
            "preset_sizes": ["1024x1024", "1024x1792", "1792x1024"],
            "allow_custom_size": False,
            "input_capabilities": {
                "whole_edit": True,
                "masked_edit": True,
                "multi_reference": True,
                "max_input_images": 4
            }
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/v1/image-generation-models",
        headers=headers,
        json=model_config
    )

    if response.status_code not in (200, 201):
        raise Exception(f"创建模型失败: {response.text}")

    return response.json()["model"]


def test_capability(token: str, model_id: str, operation: str) -> bool:
    """测试模型能力"""
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(
        f"{BASE_URL}/api/v1/image-generation-models/{model_id}/test",
        headers=headers,
        json={"operation": operation}
    )

    if response.status_code != 200:
        print(f"  ❌ {operation} 测试失败: {response.text}")
        return False

    result = response.json()
    if result.get("ok") and result.get("passed"):
        print(f"  ✅ {operation} 测试通过")
        return True
    else:
        error = result.get("error", "未知错误")
        print(f"  ❌ {operation} 测试失败: {error}")
        return False


def main():
    print("=" * 60)
    print("AI 生图模型配置脚本")
    print("=" * 60)
    print()

    # 步骤 1: 登录
    print("步骤 1: 登录管理后台")
    username = input("管理员用户名 [superadmin]: ").strip() or "superadmin"
    password = getpass.getpass("密码: ")

    try:
        token = login(username, password)
        print("✅ 登录成功\n")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    # 步骤 2: 选择提供商
    print("步骤 2: 选择生图提供商")
    print("1. OpenAI DALL-E 3 (推荐)")
    print("2. 兼容服务 (硅基流动、零一万物等)")
    print("3. Google Gemini 2.0")

    choice = input("请选择 [1]: ").strip() or "1"

    if choice != "1":
        print("暂时只支持 OpenAI DALL-E 3 自动配置")
        print("请手动通过 Web 界面配置其他提供商")
        sys.exit(1)

    # 步骤 3: 输入 API 密钥
    print("\n步骤 3: 输入 API 密钥")
    api_key = getpass.getpass("OpenAI API Key (sk-...): ").strip()

    if not api_key.startswith("sk-"):
        print("❌ API 密钥格式不正确")
        sys.exit(1)

    # 步骤 4: 创建模型
    print("\n步骤 4: 创建模型配置")
    try:
        model = create_openai_model(token, api_key)
        model_id = model["model_id"]
        print(f"✅ 模型创建成功: {model['name']} (ID: {model_id})\n")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    # 步骤 5: 运行能力测试
    print("步骤 5: 运行能力测试")
    print("注意：测试会实际调用 API，请确保账户有余额")
    confirm = input("是否继续？[Y/n]: ").strip().lower()

    if confirm and confirm != 'y':
        print("\n⚠️  跳过能力测试")
        print("请手动在 Web 界面中运行测试：")
        print(f"  1. 访问 {BASE_URL}")
        print("  2. 进入「大模型配置」→「生图模型」")
        print(f"  3. 找到模型「{model['name']}」")
        print("  4. 点击「测试」按钮，依次测试以下能力：")
        print("     - 整图编辑 (whole_edit)")
        print("     - 局部修图 (masked_edit)")
        print("     - 多图参考 (multi_reference)")
        print("\n配置完成后，刷新「AI 生图」页面即可看到 4 个模式标签。")
        sys.exit(0)

    print("\n开始测试...")
    operations = [
        ("text_to_image", "文生图"),
        ("whole_edit", "整图编辑"),
        ("masked_edit", "局部修图"),
        ("multi_reference", "多图参考")
    ]

    passed_count = 0
    for operation, label in operations:
        print(f"\n测试 {label} ({operation})...")
        if test_capability(token, model_id, operation):
            passed_count += 1
        else:
            print(f"  提示：某些提供商可能不支持所有编辑功能")

    # 步骤 6: 总结
    print("\n" + "=" * 60)
    print("配置完成")
    print("=" * 60)
    print(f"✅ 模型已创建: {model['name']}")
    print(f"✅ 通过测试: {passed_count}/{len(operations)} 个能力")
    print()
    print("下一步：")
    print(f"1. 访问 {BASE_URL}")
    print("2. 进入左侧菜单「AI 生图」")
    print("3. 刷新页面（F5）")
    print("4. 应该能看到以下模式标签：")

    if passed_count >= 3:
        print("   [ 文生图 ] [ 整图编辑 ] [ 局部编辑 ] [ 多图参考 ]")
    else:
        print("   [ 文生图 ]")
        print("   (编辑功能需要重新测试)")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户取消操作")
        sys.exit(1)
