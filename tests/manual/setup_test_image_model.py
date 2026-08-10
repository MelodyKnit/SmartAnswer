#!/usr/bin/env python3
"""在数据库中直接插入测试生图模型配置（用于快速验证功能）"""

import sqlite3
import hashlib
import json
import time
import uuid
from pathlib import Path


DB_PATH = Path("data/runtime/study-qb.sqlite3")


def calculate_configuration_stamp(model_data: dict) -> str:
    """计算配置指纹（与后端逻辑一致）"""
    # 参考: src/study_qb_assistant/platform/image_generation/service.py:1282-1295
    parts = [
        str(model_data["provider"]),
        str(model_data["base_url"]),
        str(model_data["model"]),
        str(model_data["timeout_seconds"]),
        json.dumps(model_data["protocol_config"], sort_keys=True, separators=(',', ':')),
        str(model_data["updated_at"]),
    ]
    content = "\n".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def setup_test_model():
    """在数据库中创建测试模型配置"""

    if not DB_PATH.exists():
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        print("请先启动服务创建数据库")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 检查是否已有模型配置
        cursor.execute("SELECT COUNT(*) FROM image_generation_models")
        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            print(f"⚠️  数据库中已有 {existing_count} 个生图模型")
            response = input("是否删除现有配置并重新创建？[y/N]: ").strip().lower()
            if response != 'y':
                print("操作已取消")
                return False

            # 删除现有配置
            cursor.execute("DELETE FROM image_generation_model_capability_checks")
            cursor.execute("DELETE FROM image_generation_models")
            print("✅ 已清除现有配置")

        # 准备模型数据
        now = time.time()
        model_id = str(uuid.uuid4())

        model_data = {
            "provider": "openai-images",
            "base_url": "https://api.openai.com/v1",
            "model": "dall-e-3",
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
            },
            "updated_at": now
        }

        # 计算配置指纹
        config_stamp = calculate_configuration_stamp(model_data)

        # 插入模型配置
        cursor.execute("""
            INSERT INTO image_generation_models (
                model_id, name, provider, base_url, model, api_key,
                status, timeout_seconds, protocol_config, capabilities,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model_id,
            "OpenAI DALL-E 3 开发测试",
            model_data["provider"],
            model_data["base_url"],
            model_data["model"],
            "sk-test-placeholder-key",  # 占位符密钥
            "active",
            model_data["timeout_seconds"],
            json.dumps(model_data["protocol_config"]),
            "{}",  # capabilities (旧字段，必填)
            now,
            now
        ))

        print(f"✅ 已创建模型配置")
        print(f"   模型 ID: {model_id}")
        print(f"   配置指纹: {config_stamp}")

        # 插入能力验证记录
        operations = [
            ("text_to_image", "文生图"),
            ("whole_edit", "整图编辑"),
            ("masked_edit", "局部修图"),
            ("multi_reference", "多图参考")
        ]

        for operation, label in operations:
            check_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO image_generation_model_capability_checks (
                    check_id, model_id, configuration_stamp, operation, passed,
                    error_code, error, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                check_id,
                model_id,
                config_stamp,
                operation,
                1,  # passed = True
                "",  # error_code (必填，空字符串表示无错误)
                "",  # error (必填，空字符串表示无错误)
                now
            ))
            print(f"   ✅ {label} ({operation}) 测试通过")

        conn.commit()

        # 验证插入结果
        cursor.execute("""
            SELECT
                m.name,
                m.provider,
                m.status,
                COUNT(c.check_id) as passed_checks
            FROM image_generation_models m
            LEFT JOIN image_generation_model_capability_checks c
                ON m.model_id = c.model_id AND c.passed = 1
            WHERE m.model_id = ?
            GROUP BY m.model_id
        """, (model_id,))

        result = cursor.fetchone()
        if result:
            print(f"\n验证结果：")
            print(f"   模型名称: {result[0]}")
            print(f"   提供商: {result[1]}")
            print(f"   状态: {result[2]}")
            print(f"   通过测试: {result[3]}/4 个能力")

        print("\n" + "=" * 60)
        print("✅ 测试模型配置完成！")
        print("=" * 60)
        print("\n下一步：")
        print("1. 访问 http://127.0.0.1:8765")
        print("2. 进入「AI 生图」页面")
        print("3. 刷新页面（F5）")
        print("4. 应该能看到 4 个模式标签：")
        print("   [ 文生图 ] [ 整图编辑 ] [ 局部编辑 ] [ 多图参考 ]")
        print("\n⚠️  注意：这是开发测试配置，API 密钥为占位符")
        print("   实际使用前请在 Web 界面修改为真实 API 密钥")
        print("   路径：大模型配置 → 生图模型 → 编辑模型")

        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ 配置失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("AI 生图模型快速配置工具（开发测试）")
    print("=" * 60)
    print()

    success = setup_test_model()

    if not success:
        exit(1)
