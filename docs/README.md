# 文档导航

这里存放项目长期维护的设计、运行和接口文档。根目录 [README](../README.md) 只保留项目介绍与常用命令；具体说明按主题归档到本目录，避免同一主题存在多份并行入口。

## 快速入口

- [环境与依赖](setup/environment.md)：Conda、Node.js、开发服务与环境变量。
- [部署说明](deployment.md)：Docker Compose、运行数据和生产部署检查。
- [系统架构](architecture/architecture.md)：模块边界、运行时组装和主要数据流。
- [API 契约](architecture/api-contract.md)：`/api/v1`、`/ocs/query` 与主要请求响应约定。
- [验收流程](process/acceptance.md)：本地与发布前验证路径。

## 架构与平台

- [系统设计规范](architecture/system-design-specification.md)
- [工作台接口覆盖](architecture/dashboard-interface-coverage.md)
- [技术栈决策](architecture/stack-decision.md)

## 服务与集成

- [本地服务](services/local-service.md)
- [模型提供商与调用链](services/model-provider.md)
- [OCS 适配](services/ocs-adapter.md)
- [OCS 使用说明](services/ocs-usage-cn.md)
- [外部客户端适配](services/external-client-adapter.md)
- [AI 生图](services/image-generation.md)
- [生图方案比较](services/image-generation-comparison.md)
- [生图优化记录](services/image-generation-optimization.md)

## 数据与题库

- [数据来源](setup/data-sources.md)
- [导入映射](setup/ingestion-mapping.md)
- [标准化索引](setup/normalized-indexes.md)
- [来源校验](setup/source-verification.md)

## 过程记录

- [研究记录](process/research.md)
- [实施计划](process/implementation-plan.md)

## 维护约定

- 新增长期文档时，同时更新本页对应分类的链接。
- 同一主题只保留一个可维护的主文档；迁移期间的旧路径应明确指向主文档，而不是继续独立演进。
- 一次性排查报告、截图、实验输出和本地测试数据放在 `.local/` 或运行数据目录，不提交到 Git。
- 可复用的开发入口应在相邻目录保留简短 README，例如[后端包说明](../src/study_qb_assistant/README.md)、[脚本说明](../scripts/README.md)和[测试说明](../tests/README.md)。
