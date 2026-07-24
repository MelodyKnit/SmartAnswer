"""生图队列后台工作器。"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from ...logger import log_event
from .service import ImageGenerationService


class ImageGenerationWorker:
    """以单消费者方式处理数据库队列，避免对供应商重复提交。"""

    def __init__(self, service: ImageGenerationService, *, poll_interval_seconds: float = 1.0) -> None:
        self.service = service
        self.poll_interval_seconds = max(0.2, poll_interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._cleanup_ticks = 0

    async def start(self) -> None:
        """恢复中断任务并启动后台轮询。"""

        if self._task is not None:
            return
        recovered = await asyncio.to_thread(self.service.recover_abandoned_jobs)
        if recovered:
            log_event("image_generation_recovered_jobs", {"count": recovered})
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="image-generation-worker")

    async def stop(self) -> None:
        """停止轮询，不主动中断已提交给供应商的同步执行。"""

        self._stop_event.set()
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def run_once(self) -> bool:
        """执行一次轮询，供测试和受控维护任务复用。"""

        processed = await asyncio.to_thread(self.service.process_next_job)
        self._cleanup_ticks += 1
        if self._cleanup_ticks >= 60:
            self._cleanup_ticks = 0
            removed = await asyncio.to_thread(self.service.cleanup_expired_assets)
            if removed:
                log_event("image_generation_assets_cleaned", {"count": removed})
        return processed

    async def _run(self) -> None:
        """持续轮询队列；空队列时等待，避免忙循环。"""

        while not self._stop_event.is_set():
            try:
                processed = await self.run_once()
            except Exception as exc:
                # 单次数据库或文件系统故障不能让常驻工作器永久退出；下一轮会继续尝试。
                log_event(
                    "image_generation_worker_iteration_failed",
                    {"error_type": type(exc).__name__},
                )
                processed = False
            if not processed:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.poll_interval_seconds
                    )
                except TimeoutError:
                    continue
