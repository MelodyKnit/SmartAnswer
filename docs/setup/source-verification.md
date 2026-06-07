# 数据源验证

更新日期：`2026-06-07`

## 1. 目的

本文档记录了哪些公开数据源已通过权威证据进行了验证、适用何种许可证条件、数据是否在本地可用，以及该源是否适合直接导入到项目中。

## 2. 已验证的数据源状态

### 2.1 C-Eval

- 仓库：<https://github.com/hkust-nlp/ceval>
- 本地路径：[data/raw/ceval-upstream](../data/raw/ceval-upstream)
- 权威证据：
  - GitHub 仓库元数据报告的代码许可证为 `MIT`
  - 本地仓库包含 `LICENSE-DATA`
  - 本地 `README.md` 说明该数据集包含 `52` 个学科的 `13,948` 道单项选择题
- 重要许可证说明：
  - 本地 `LICENSE-DATA` 中的数据集许可证为 `CC BY-NC-SA 4.0`
- 当前本地状态：
  - 仓库克隆成功
  - 数据集载荷未直接打包在仓库中
  - 官方 README 指向 Hugging Face 压缩包以及 datasets 加载方式
- 导入适合度：
  - 适合内部非商业研究导入
  - 不适合无限制的重新分发
- 当前限制：
  - 在本会话期间，当前环境无法直接访问 Hugging Face 下载路径

### 2.2 CMMLU

- 仓库：<https://github.com/haonan-li/CMMLU>
- 本地路径：[data/raw/cmmlu-upstream](../data/raw/cmmlu-upstream)
- 权威证据：
  - 本地 `README_EN.md` 说明 CMMLU 涵盖 `67` 个主题
  - 本地仓库包含一个带有 CSV 文件的 `data/` 目录
  - 本地 `README_EN.md` 的许可证章节指向 `Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License`（知识共享 署名-非商业性使用-相同方式共享 4.0 国际许可证）
  - 本地样本文件：[anatomy.csv](../data/raw/cmmlu-upstream/data/dev/anatomy.csv)
- 重要许可证说明：
  - 本地 `README_EN.md` 声明该数据集基于 `CC BY-NC-SA 4.0` 授权
- 当前本地状态：
  - 仓库克隆成功
  - 本地 `data/` 下找到 `134` 个文件
  - 格式可直接用于导入规划
- 导入适合度：
  - 非商业研究模式下首批结构化导入的强力候选

### 2.3 M3KE

- 仓库：<https://github.com/tjunlp-lab/M3KE>
- 本地路径：[data/raw/m3ke-upstream](../data/raw/m3ke-upstream)
- 权威证据：
  - 本地 `README.md` 说明 M3KE 包含来自 `71` 个任务的 `20,477` 道题目
  - 本地 `README.md` 说明所有题目均为包含四个选项的单项选择题
  - 本地仓库包含一个带有 JSONL 文件和 `M3KE.zip` 的 `data/` 目录
  - 本地样本文件：[Advanced Mathematics-Natural Sciences-College.jsonl](../data/raw/m3ke-upstream/data/dev/Advanced%20Mathematics-Natural%20Sciences-College.jsonl)
- 重要许可证说明：
  - 本地 `README.md` 中未发现明确的数据集许可证章节
  - GitHub 仓库元数据未公开许可证信息
- 当前本地状态：
  - 仓库克隆成功
  - 本地 `data/` 下找到 `143` 个文件
  - 数据格式可直接导入
- 导入适合度：
  - 技术上表现强力的导入候选
  - 法律复用状态必须被视为“需要人工许可证确认”

### 2.4 AGIEval

- 仓库：<https://github.com/ruixiangcui/AGIEval>
- 本地路径：[data/raw/agieval-upstream](../data/raw/agieval-upstream)
- 权威证据：
  - GitHub 仓库元数据报告的代码许可证为 `MIT`
  - 本地 `README.md` 说明 AGIEval v1.1 包含 `20` 个任务
  - 本地 `README.md` 说明 AGIEval v1.1 包含 `18` 个多选题（MCQ）任务和两个填空题任务
  - 本地仓库包含带有 JSONL 任务文件和 few-shot 提示词的 `data/` 目录
  - 本地样本文件：[gaokao-physics.jsonl](../data/raw/agieval-upstream/data/v1_1/gaokao-physics.jsonl)
- 重要许可证说明：
  - 本地 `README.md` 说明数据的使用应遵循原始数据集的许可证
  - 视为混合许可证，在重新分发前需按任务进行审查
- 当前本地状态：
  - 仓库克隆成功
  - 本地 `data/` 下找到 `46` 个文件
  - 已将 `6154` 条多选题（MCQ）记录导出到 `data\normalized\agieval-mcq.jsonl`
- 导入适合度：
  - 适用于评估和模式（schema）测试
  - 不应被视为单一许可证的可分发语料库

## 3. 平台验证快照

### 3.1 MaxKB

- 仓库：<https://github.com/1Panel-dev/MaxKB>
- GitHub 仓库元数据：
  - 许可证：`GPL-3.0`
  - 默认分支：`v2`
  - 最近检查的更新时间：`2026-06-06T23:17:57Z`
- 此前使用的文档证据：
  - 官方文档描述了数据集导入和 API 对话功能
- 当前判定：
  - 如果后续需要一个可维护的 Web UI 和知识库管理工作流，它是最强的可选产品主导层（product-led layer）

### 3.2 FastGPT

- 仓库：<https://github.com/labring/FastGPT>
- GitHub 仓库元数据：
  - 许可证字段报告为：`NOASSERTION`
  - 最近检查的更新时间：`2026-06-07T02:06:34Z`
- 当前判定：
  - 强力的工作流和问答导入候选
  - 在生产环境采用前，应直接从仓库中阅读许可证条款

### 3.3 Open WebUI

- 仓库：<https://github.com/open-webui/open-webui>
- GitHub 仓库元数据：
  - 许可证字段报告为：`NOASSERTION`
  - 最近检查的更新时间：`2026-06-07T04:49:15Z`
- 当前判定：
  - 强力的轻量级原型路径
  - 在更深入采用前，直接验证仓库的许可证文本

### 3.4 Dify

- 仓库：<https://github.com/langgenius/dify>
- GitHub 仓库元数据：
  - 许可证字段报告为：`NOASSERTION`
  - 最近检查的更新时间：`2026-06-07T04:49:29Z`
- 当前判定：
  - 强力的编排平台
  - 在更深入采用前，直接验证仓库的许可证文本

## 4. 推荐的数据源优先级

在实现中采用以下顺序：

1. 经过人工验证的小型 CSV
2. CMMLU，用于首批结构化批量导入
3. M3KE，用于许可证确认后的大规模导入测试
4. AGIEval，用于评估和模式加固
5. C-Eval，在数据载荷下载路径可用后的完整数据集

## 5. 当前可靠性说明

该项目现在本地已备有三个源的公开基准测试数据（存放于 `raw/` 目录下）以及 C-Eval 仓库材料。这已足够在无需等待额外网络探索的情况下，开始导入流水线的开发。
