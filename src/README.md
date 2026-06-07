# 源码布局

未来的实现代码应该存放在这里。

建议的划分：

```text
src/
  api/
  domain/
  providers/
  retrieval/
  ingestion/
  schemas/
```

准则：

- 将传输逻辑与检索和提供商（provider）模块隔离开来
- 确保提供商适配器隐藏在稳定的接口后面
- 确保模式（schema）定义明确且可重用
