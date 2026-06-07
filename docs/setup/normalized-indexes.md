# 规范化索引

更新日期：`2026-06-07`

## 1. 目的

本文档记录了从已下载的公开源生成的规范化本地索引。

## 2. 当前索引

### CMMLU

- 路径：`data\normalized\cmmlu.jsonl`
- 记录数：`11917`
- 来源：`CMMLU`
- 许可证说明：`CC BY-NC-SA 4.0`
- 推荐用途：默认的本地学习服务索引

### AGIEval MCQ

- 路径：`data\normalized\agieval-mcq.jsonl`
- 记录数：`6154`
- 来源：`AGIEval`
- 许可证说明：上游混合许可证；在完成任务级许可证审查之前，仅用于本地评估以及模式（schema）加固
- 推荐用途：可选的扩展索引

### Verified Combined（验证合并）

- 路径：`data\normalized\verified.jsonl`
- 记录数：`18071`
- 来源：
  - `CMMLU`：`11917`
  - `AGIEval`：`6154`
- 推荐用途：更广泛的本地查找测试

## 3. 重新生成

当前本地索引来源：

- `data\normalized\cmmlu.jsonl`
- `data\normalized\agieval-mcq.jsonl`
- `data\normalized\verified.jsonl`

## 4. 服务使用

默认启动方式：

```powershell
.\scripts\run.ps1
```

使用更广泛的已验证索引：

```powershell
.\scripts\run.ps1
```

开发模式热重载：

```powershell
.\scripts\run-dev.ps1
```
