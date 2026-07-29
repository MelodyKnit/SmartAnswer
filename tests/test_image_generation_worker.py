"""生图后台工作器的生命周期与故障隔离测试。"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from study_qb_assistant.api.app import create_app
from study_qb_assistant.auth import AuthService
from study_qb_assistant.bootstrap import runtime_lifespan
from study_qb_assistant.platform.container import PlatformServices
from study_qb_assistant.platform.image_generation.worker import ImageGenerationWorker
from study_qb_assistant.search import LocalQuestionIndex


class WorkerService:
    """工作器生命周期所需的最小同步服务替身。"""

    def __init__(self) -> None:
        self.calls = 0
        self.recovered = False

    def recover_abandoned_jobs(self) -> int:
        """模拟启动阶段没有遗留任务。"""

        self.recovered = True
        return 0

    def process_next_job(self) -> bool:
        """供 run_once 测试使用。"""

        self.calls += 1
        return True

    def cleanup_expired_assets(self) -> int:
        """测试中不需要清理资产。"""

        return 0


class ControlledImageGenerationWorker(ImageGenerationWorker):
    """不进入线程池的受控工作器，用于验证循环故障恢复。"""

    async def run_once(self) -> bool:
        """首轮异常，第二轮请求退出，验证异常不终止工作器。"""

        self.service.calls += 1
        if self.service.calls == 1:
            raise RuntimeError("temporary database error")
        self._stop_event.set()
        return False


class ImageGenerationWorkerTests(unittest.IsolatedAsyncioTestCase):
    """确认工作器的轮询和异常隔离行为。"""

    async def test_run_once_dispatches_synchronous_job_processing(self) -> None:
        """单次轮询应通过线程池调用同步任务服务。"""

        service = WorkerService()
        worker = ImageGenerationWorker(service)

        self.assertTrue(await worker.run_once())
        self.assertEqual(service.calls, 1)

    async def test_start_and_stop_complete_without_leaving_a_task(self) -> None:
        """真实生命周期应能完成恢复、空队列等待与取消退出。"""

        class IdleService(WorkerService):
            def process_next_job(self) -> bool:
                self.calls += 1
                return False

        service = IdleService()
        worker = ImageGenerationWorker(service, poll_interval_seconds=0.2)
        await worker.start()
        await asyncio.sleep(0.02)
        await worker.stop()

        self.assertTrue(service.recovered)
        self.assertIsNone(worker._task)

    async def test_worker_recovers_after_iteration_error(self) -> None:
        """异常后下一轮仍会继续执行，而不是让常驻循环退出。"""

        service = WorkerService()
        worker = ControlledImageGenerationWorker(service, poll_interval_seconds=0.2)
        await worker._run()

        self.assertGreaterEqual(service.calls, 2)


class RuntimeLifespanTests(unittest.TestCase):
    """验证真实 FastAPI 生命周期会管理生图后台工作器。"""

    def test_runtime_lifespan_starts_and_stops_image_worker(self) -> None:
        """应用启动后创建工作器，退出后不遗留后台任务引用。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"STQB_DATA_DIR": directory}, clear=False
        ):
            database_path = Path(directory) / "runtime-lifespan.sqlite3"
            auth = AuthService(database_path)
            services = PlatformServices(database_path)
            app = create_app(
                LocalQuestionIndex(()),
                auth_service=auth,
                platform_services=services,
                require_auth=True,
                lifespan=runtime_lifespan,
            )

            with TestClient(app) as client:
                response = client.get("/api/v1/healthz")
                self.assertEqual(response.status_code, 200)
                self.assertIsNotNone(app.state.image_generation_worker._task)

            self.assertIsNone(app.state.image_generation_worker._task)


if __name__ == "__main__":
    unittest.main()
