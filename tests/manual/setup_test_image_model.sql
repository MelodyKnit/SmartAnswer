-- 快速设置生图模型的 SQL 脚本（用于开发测试）

-- 1. 插入测试模型配置
INSERT INTO image_generation_models (
    model_id, name, provider, base_url, model, api_key,
    status, timeout_seconds, protocol_config, capabilities,
    created_at, updated_at
) VALUES (
    'test-dalle-3-001',
    'OpenAI DALL-E 3 测试模型',
    'openai-images',
    'https://api.openai.com/v1',
    'dall-e-3',
    'sk-test-key-for-development',
    'active',
    120,
    json('{"output_config": {"mode": "preset-sizes", "preset_sizes": ["1024x1024", "1024x1792", "1792x1024"]}, "input_capabilities": {"whole_edit": true, "masked_edit": true, "multi_reference": true, "max_input_images": 4}}'),
    NULL,
    CAST(strftime('%s', 'now') AS REAL),
    CAST(strftime('%s', 'now') AS REAL)
);

-- 2. 计算配置指纹（用于能力验证）
-- configuration_stamp = sha256(provider + base_url + model + timeout + protocol_config + updated_at)
-- 实际值需要用 Python 计算，这里使用占位符

-- 3. 插入能力测试通过记录
INSERT INTO image_generation_model_capability_checks (
    check_id, model_id, configuration_stamp, operation, passed,
    error_code, error, checked_at
) VALUES
    ('check-001', 'test-dalle-3-001', 'test-config-stamp', 'text_to_image', 1, NULL, NULL, CAST(strftime('%s', 'now') AS REAL)),
    ('check-002', 'test-dalle-3-001', 'test-config-stamp', 'whole_edit', 1, NULL, NULL, CAST(strftime('%s', 'now') AS REAL)),
    ('check-003', 'test-dalle-3-001', 'test-config-stamp', 'masked_edit', 1, NULL, NULL, CAST(strftime('%s', 'now') AS REAL)),
    ('check-004', 'test-dalle-3-001', 'test-config-stamp', 'multi_reference', 1, NULL, NULL, CAST(strftime('%s', 'now') AS REAL));

-- 4. 验证插入结果
SELECT
    m.name,
    m.provider,
    m.status,
    COUNT(c.check_id) as passed_checks
FROM image_generation_models m
LEFT JOIN image_generation_model_capability_checks c
    ON m.model_id = c.model_id AND c.passed = 1
WHERE m.model_id = 'test-dalle-3-001'
GROUP BY m.model_id;
