# Platform 结构

平台能力按业务域拆分，不再提供承担全部职责的 `PlatformService`。

## 组装

- `container.py` 定义 `PlatformServices`，只创建领域仓储和领域服务。
- `base.py` 提供领域服务共享的仓储引用和进程内事务锁。
- API 依赖从 `PlatformServices` 中按领域取得服务，不通过转发方法调用。

## 领域

- `tokens/`：API Key 生命周期与 OCS 配置生成。
- `usage/`：调用记录与统计。
- `feedback/`：反馈提交和处理。
- `wallet/`：积分、流水和兑换码。
- `notifications/`、`announcements/`：通知中心与公告。
- `import_scripts/`：导入脚本模板和生成。
- `permissions/`：角色权限。
- `settings/`：系统配置和运行时配置映射。
- `dashboard/`：跨域只读工作台聚合。

## 约束

- 单一业务规则放在所属领域服务中。
- 跨域流程必须显式注入所需服务，不重新建立万能 Facade。
- 记录类型与展示辅助放在所属领域目录，不集中堆放互不相关的数据结构。
- 数据持久化由 `storage/repositories` 中的对应领域仓储负责。
