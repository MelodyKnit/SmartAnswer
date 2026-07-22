"""运行时项目更新巡检任务。"""

from __future__ import annotations

import asyncio
from typing import Protocol

from ...logger import log_event


class ProjectUpdateCycleService(Protocol):
    """后台巡检需要的最小项目更新服务契约。"""

    def background_cycle(self) -> None:
        """执行一次更新状态恢复与周期检查。"""


class ProjectUpdateMonitor:
    """在单个应用实例内周期执行更新状态恢复与 Release 巡检。"""

    def __init__(self, service: ProjectUpdateCycleService, *, tick_seconds: float = 15.0) -> None:
        self.service = service
        self.tick_seconds = tick_seconds
        self.stop_event: asyncio.Event | None = None
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动巡检协程；重复调用不会创建多个后台任务。"""

        if self.task is not None and not self.task.done():
            return
        self.stop_event = asyncio.Event()
        self.task = asyncio.create_task(self.run(), name="project-update-monitor")

    async def stop(self) -> None:
        """停止巡检协程，避免应用关闭后继续访问 GitHub。"""

        if self.stop_event is not None:
            self.stop_event.set()
        if self.task is not None:
            await self.task
        self.task = None
        self.stop_event = None

    async def run(self) -> None:
        """持续运行巡检；单次网络失败不会中断后续检查。"""

        while self.stop_event is not None and not self.stop_event.is_set():
            try:
                await asyncio.to_thread(self.service.background_cycle)
            except Exception as exc:  # 防止后台巡检异常影响 FastAPI 生命周期。
                log_event("project_update_monitor_failed", {"error": str(exc)[:500]})
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.tick_seconds)
            except TimeoutError:
                continue
