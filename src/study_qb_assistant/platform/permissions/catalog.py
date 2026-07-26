"""平台权限目录与系统内置角色定义。

权限是后端可执行能力的稳定标识。角色只保存这些标识的组合，前端通过接口
读取目录展示名称和分组，避免在多个页面维护同一份权限清单。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    """单个可授权的平台能力。"""

    key: str
    group: str
    group_label: str
    label: str
    description: str
    icon: str

    def to_dict(self) -> dict[str, str]:
        """转换为 API 可消费的权限目录项。"""

        return {
            "key": self.key,
            "group": self.group,
            "group_label": self.group_label,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
        }


PERMISSION_CATALOG: tuple[PermissionDefinition, ...] = (
    PermissionDefinition("dashboard:all", "dashboard", "控制台权限", "查看全部看板", "查看全站控制台看板数据", "DataBoard"),
    PermissionDefinition("dashboard:self", "dashboard", "控制台权限", "查看个人看板", "查看个人控制台看板数据", "DataBoard"),
    PermissionDefinition("users:write", "users", "用户与角色", "管理用户", "修改普通用户的状态与积分", "User"),
    PermissionDefinition("roles:read", "users", "用户与角色", "查看角色权限", "查看角色与权限配置", "User"),
    PermissionDefinition("roles:write", "users", "用户与角色", "维护角色权限", "在授权范围内维护自定义角色权限", "User"),
    PermissionDefinition("questions:read", "questions", "题库管理", "查看题库", "查看题库列表和题目详情", "Collection"),
    PermissionDefinition("questions:write", "questions", "题库管理", "维护题库", "新增、编辑、删除题库题目", "Collection"),
    PermissionDefinition("billing:read", "wallet", "钱包与积分", "查看计费规则", "查看系统积分扣费规则", "Wallet"),
    PermissionDefinition("billing:write", "wallet", "钱包与积分", "修改计费规则", "修改系统积分策略配置", "Wallet"),
    PermissionDefinition("wallet:changes:read", "wallet", "钱包与积分", "查看积分流水", "查看用户积分变动记录", "Wallet"),
    PermissionDefinition("wallet:changes:write", "wallet", "钱包与积分", "管理积分与兑换码", "发放积分、创建和管理兑换码", "Wallet"),
    PermissionDefinition("system:read", "system", "系统管理", "查看系统日志", "查看系统运行日志与状态信息", "Setting"),
    PermissionDefinition("system:write", "system", "系统管理", "修改系统配置", "修改系统配置、积分策略和服务协议", "Setting"),
    PermissionDefinition("announcements:read", "announcements", "公告管理", "查看公告", "查看公告列表和发布状态", "BellFilled"),
    PermissionDefinition("announcements:write", "announcements", "公告管理", "管理公告", "创建、编辑和归档系统公告", "BellFilled"),
    PermissionDefinition("import-scripts:read", "scripts", "导入脚本", "查看导入脚本", "查看脚本模板和生成记录", "Document"),
    PermissionDefinition("import-scripts:write", "scripts", "导入脚本", "管理导入脚本", "创建、编辑和发布导入脚本", "Document"),
    PermissionDefinition("llm:read", "llm", "大模型配置", "查看大模型配置", "查看模型、联网搜索和调用追溯", "Cpu"),
    PermissionDefinition("llm:write", "llm", "大模型配置", "管理大模型配置", "维护模型配置、搜索引擎和答题策略", "Cpu"),
    PermissionDefinition("tokens:self", "personal", "个人中心", "管理个人令牌", "创建、查看、撤销自己的 API Key", "Key"),
    PermissionDefinition("feedback:self", "personal", "个人中心", "提交个人反馈", "提交题目纠错和使用反馈", "Key"),
    PermissionDefinition("feedback:manage", "personal", "个人中心", "处理用户反馈", "查看和处理全站题目反馈", "Key"),
    PermissionDefinition("image-generation:use", "personal", "个人中心", "使用 AI 生图", "使用已启用的图片生成模型", "Picture"),
)

PERMISSION_KEYS = frozenset(item.key for item in PERMISSION_CATALOG)


@dataclass(frozen=True, slots=True)
class SystemRoleDefinition:
    """系统不可删除角色的初始定义。"""

    role_id: str
    name: str
    description: str
    permissions: tuple[str, ...]


SYSTEM_ROLE_DEFINITIONS: tuple[SystemRoleDefinition, ...] = (
    SystemRoleDefinition(
        "superadmin",
        "超级管理员",
        "平台最高权限，可维护系统与角色归属",
        tuple(item.key for item in PERMISSION_CATALOG),
    ),
    SystemRoleDefinition(
        "admin",
        "管理员",
        "负责运营、题库、积分与接入维护",
        (
            "dashboard:all",
            "users:write",
            "roles:read",
            "billing:read",
            "wallet:changes:read",
            "wallet:changes:write",
            "import-scripts:read",
            "import-scripts:write",
            "questions:read",
            "questions:write",
            "llm:read",
            "announcements:read",
            "announcements:write",
            "feedback:manage",
            "image-generation:use",
        ),
    ),
    SystemRoleDefinition(
        "user",
        "普通用户",
        "基础学习、令牌与反馈能力",
        ("dashboard:self", "tokens:self", "feedback:self", "image-generation:use"),
    ),
)

SYSTEM_ROLE_IDS = frozenset(item.role_id for item in SYSTEM_ROLE_DEFINITIONS)
