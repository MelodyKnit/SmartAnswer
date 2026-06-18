# 工作台功能覆盖分析

更新时间：`2026-06-08`

## 1. 目的

本文件用于把工作台截图中的功能块，与当前后端接口的真实覆盖情况逐项对照。

输出目标：

- 哪些功能已经有接口支撑
- 哪些功能还缺接口
- 当前已经实现到了什么覆盖程度

## 2. 截图中的功能块

根据截图，工作台和左侧菜单涉及这些业务域：

- 工作台首页聚合
- API Key 管理
- 导入脚本
- 使用记录
- 兑换管理
- 用户管理
- 角色权限
- 系统配置
- 常用功能快捷入口
- 排行统计
- 消息列表

## 3. 已有接口覆盖

### 3.1 已完全覆盖

- API Key 管理
  - `GET /tokens`
  - `POST /tokens`
  - `POST /tokens/{token_id}/revoke`
- 使用记录
  - `GET /usage-logs`
- 用户管理
  - `GET /users`
  - `PATCH /users/{username}`
- 系统配置
  - `GET /system-config`
  - `PATCH /system-config`
- 钱包/积分流水与兑换码
  - `GET /wallet/me`
  - `GET /wallet/orders`
  - `POST /wallet/grants`
  - `GET /wallet/redeem-codes`
  - `POST /wallet/redeem-codes`
  - `POST /wallet/redeem`

### 3.2 当前已补齐

- 工作台首页聚合
  - `GET /dashboard/workbench`
- 排行统计
  - `GET /dashboard/rankings`
- 消息列表
  - `GET /notifications`
  - `POST /notifications/{notification_id}/read`
  - `POST /notifications/read-all`
- 导入脚本
  - `GET /import-scripts`
  - `POST /import-scripts/generate`
  - `GET /import-scripts/{script_id}`
  - `DELETE /import-scripts/{script_id}`
- 兑换管理
  - `GET /wallet/redeem-codes`
  - `POST /wallet/redeem-codes`
  - `GET /wallet/changes`
  - `POST /wallet/grants`
- 角色权限
  - `GET /roles`
  - `GET /roles/{role_id}/permissions`
  - `PUT /roles/{role_id}/permissions`

## 4. 当前仍是“部分覆盖”的点

以下功能虽然已经有后端接口，但还属于基础版，不是完整产品态：

- 工作台首页聚合
  - 当前返回的是后端可计算聚合数据
  - 还没有真正的前端组件级字段约束版本化
- 排行统计
  - 当前默认按调用来源/Token 维度聚合
  - 后续可扩展更丰富的维度
- 导入脚本
  - 当前已支持生成和查询
  - 后续可继续扩展模板类型
- 角色权限
  - 当前已支持读取与更新
  - 仍属于轻量权限矩阵

## 5. 接口覆盖结论

如果以截图中的“页面需要有后端接口支撑”为标准，当前项目已经从“基础平台接口”扩展到了“能够支撑工作台和左侧菜单的完整接口骨架”。

当前结论：

- 基础账号、令牌、使用记录、钱包、系统配置：已覆盖
- 工作台聚合、排行、消息中心：已覆盖
- 导入脚本：已覆盖；接入管理已下线，不再作为独立功能
- 兑换管理、角色权限：已覆盖

也就是说，截图里的主要功能区块，现在都已经存在对应后端接口。

## 6. 黑盒验证依据

当前新增接口已经通过工作台管理流黑盒测试，见：

- [tests/test_fastapi_local_server.py](../../tests/test_fastapi_local_server.py)

重点覆盖：

- 创建 Token
- 生成导入脚本
- 创建积分兑换码
- 更新角色权限
- 获取工作台聚合
- 获取排行
- 获取消息并标记已读

## 7. 后续建议

下一阶段如果继续推进，不应再优先补接口数量，而应转向：

- 前后端字段对齐
- 分页、筛选、排序细化
- 消息规则自动化生成
- 兑换码与权限的更细粒度业务规则
