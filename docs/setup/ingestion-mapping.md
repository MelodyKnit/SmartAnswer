# 导入映射

更新日期：`2026-06-07`

## 1. 目的

本文档将已验证的上游源数据格式映射为 [api-contract.md](../architecture/api-contract.md) 和 [architecture.md](../architecture/architecture.md) 中描述的规范化内部题目模式（schema）。

## 2. 规范化内部字段

目标内部字段：

- `question_id`
- `title_raw`
- `question_type`
- `options_raw`
- `answer_raw`
- `explanation`
- `subject`
- `chapter`
- `tags`
- `source_name`
- `source_url`
- `source_license`
- `source_split`

## 3. CMMLU 映射

样本源：

- [anatomy.csv](../data/raw/cmmlu-upstream/data/dev/anatomy.csv)

观察到的源数据列：

- 未命名的行索引
- `Question`
- `A`
- `B`
- `C`
- `D`
- `Answer`

映射关系：

- `question_id` <- 文件名（file stem） + 行索引
- `title_raw` <- `Question`
- `question_type` <- `single`
- `options_raw` <- `[A, B, C, D]`
- `answer_raw` <- `Answer`
- `explanation` <- 空
- `subject` <- 文件名，例如 `anatomy`
- `chapter` <- 空
- `tags` <- `["cmmlu"]`
- `source_name` <- `CMMLU`
- `source_url` <- 上游仓库 URL
- `source_license` <- `CC BY-NC-SA 4.0`
- `source_split` <- 父级目录名，例如 `dev` 或 `test`

导入难度：

- 低

## 4. M3KE 映射

样本源：

- [Advanced Mathematics-Natural Sciences-College.jsonl](../data/raw/m3ke-upstream/data/dev/Advanced%20Mathematics-Natural%20Sciences-College.jsonl)

观察到的源数据字段：

- `id`
- `question`
- `A`
- `B`
- `C`
- `D`
- `answer`

映射关系：

- `question_id` <- 文件名 + `id`
- `title_raw` <- `question`
- `question_type` <- `single`
- `options_raw` <- `[A, B, C, D]`
- `answer_raw` <- `answer`
- `explanation` <- 空
- `subject` <- 从文件名中提取（解析第一个分隔符之前的分组）
- `chapter` <- 空
- `tags` <- 解析出的学科和等级，加上 `m3ke`
- `source_name` <- `M3KE`
- `source_url` <- 上游仓库 URL
- `source_license` <- `unknown-needs-confirmation` （未知-需要确认）
- `source_split` <- 父级目录名，例如 `dev` 或 `test`

导入难度：

- 技术上：低
- 运营上：中等（因为仍需进行许可证确认）

## 5. AGIEval 映射

样本源：

- [gaokao-physics.jsonl](../data/raw/agieval-upstream/data/v1_1/gaokao-physics.jsonl)

观察到的源数据字段：

- `passage`
- `question`
- `options`
- `label`
- `answer`
- `other`

映射关系：

- `question_id` <- 文件名 + 行号
- `title_raw` <- `question`
- `question_type` <- 多选题（MCQ）任务为 `single`
- `options_raw` <- `options`
- `answer_raw` <- 存在 `label` 时为 `label`，否则为 `answer`
- `explanation` <- 空
- `subject` <- 文件名，例如 `gaokao-physics`
- `chapter` <- 空
- `tags` <- `["agieval", "v1_1"]`
- `source_name` <- `AGIEval`
- `source_url` <- 上游仓库 URL
- `source_license` <- `mixed-follow-original` （混合许可证-遵循原版）
- `source_split` <- 版本目录名，例如 `v1_1`

特殊处理：

- 如果存在 `passage`，则将其保留在辅助元数据中，以便后续用作检索上下文
- 存在 `other.source` 时予以保留

导入难度：

- 中等（因为某些任务是非多选题（non-MCQ），且许可证期望因原始数据集而异）

## 6. C-Eval 计划映射

当前证据：

- 本地仓库包含文档和映射关系
- 完整数据集载荷通过 Hugging Face 进行引用

官方 README 示例中预期的字段：

- `id`
- `question`
- `A`
- `B`
- `C`
- `D`
- `answer`
- `explanation`

计划映射关系：

- `question_id` <- 学科处理器（subject handler） + `id`
- `title_raw` <- `question`
- `question_type` <- `single`
- `options_raw` <- `[A, B, C, D]`
- `answer_raw` <- `answer`
- `explanation` <- `explanation`
- `subject` <- 学科处理器
- `tags` <- 学科类别，加上 `ceval`
- `source_name` <- `C-Eval`
- `source_license` <- `CC BY-NC-SA 4.0`

## 7. 推荐的首批导入顺序

1. CMMLU
2. M3KE
3. AGIEval MCQ 子集
4. C-Eval（在成功检索到数据载荷后）

## 8. 直接的代码层影响

首个导入流水线应支持：

- CSV 行读取器
- JSONL 行读取器
- 文件名（file-stem）元数据解析
- 针对每个源的许可证打标
- 具有划分感知（split-aware）的出处记录
