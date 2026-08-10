# 测试说明

本目录存放项目后端的测试代码，按用途分为两类：

- **单元测试 / 自动化测试**：`tests/` 根目录及 `tests/unit/` 下的 `test_*.py`，
  由 pytest 自动收集运行，包含断言，作为回归保护。
- **主动调用脚本**：`tests/manual/` 下的脚本，需要手动执行，
  通常以 print 输出结果用于联调、验证或探索，**不参与 pytest 自动收集**。其中可能包含测试模型配置或测试 SQL，严禁用于生产数据库和 `deploy-data`。

## 常用命令

运行全部自动化测试：

```powershell
conda run -n ai-study-qb pytest -q
```

手动执行验证脚本（示例）：

```powershell
conda run -n ai-study-qb python tests/manual/test_size_inference_simple.py
```

## 目录结构

```
tests/
├── test_*.py          # 现有单元/联调测试（pytest 自动收集）
├── unit/              # 新增单元测试（pytest 自动收集）
│   └── test_error_handling.py
├── manual/            # 主动调用脚本（手动执行，pytest 不收集）
│   ├── test_size_inference_simple.py
│   ├── configure_image_model.py       # 通过管理 API 验证测试生图模型
│   ├── setup_test_image_model.py      # 直接写入本地测试 SQLite 配置
│   └── setup_test_image_model.sql     # 上述测试配置的 SQL 参考
└── README.md
```

> pytest 收集范围由 `pyproject.toml` 的 `[tool.pytest.ini_options]` 控制：
> `testpaths = ["tests"]` 且 `norecursedirs = ["tests/manual"]`。
> 新增主动调用脚本请放入 `tests/manual/`，避免被自动测试误收集。

## 覆盖范围

- OCS 查询配置与响应格式。
- 题库检索、AI 回退与搜索增强流程。
- FastAPI 用户、令牌、工作台、钱包、接入和导入脚本接口。
- 模型输出解析、搜索引擎适配和答案规范化。
- 错误处理：全局异常结构化响应、CORS 头、生图领域错误翻译（`unit/test_error_handling.py`）。
