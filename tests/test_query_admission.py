"""查题并发与速率准入控制测试。"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.query_admission import (  # noqa: E402
    QueryAdmissionController,
    normalize_query_protection,
)


class QueryAdmissionTests(unittest.TestCase):
    def test_per_user_concurrency_is_released_idempotently(self) -> None:
        controller = QueryAdmissionController()
        policy = {
            "query_rate_limit_enabled": "false",
            "query_max_active_requests_per_user": "1",
            "query_max_active_requests": "4",
        }

        lease, allowed = controller.try_acquire("user:1", policy)
        self.assertTrue(allowed.allowed)
        self.assertIsNotNone(lease)

        blocked, decision = controller.try_acquire("user:1", policy)
        self.assertIsNone(blocked)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "user_concurrency")

        lease.release()
        lease.release()
        next_lease, next_decision = controller.try_acquire("user:1", policy)
        self.assertTrue(next_decision.allowed)
        next_lease.release()

    def test_global_concurrency_is_shared_by_different_users(self) -> None:
        controller = QueryAdmissionController()
        policy = {
            "query_rate_limit_enabled": "false",
            "query_max_active_requests_per_user": "2",
            "query_max_active_requests": "1",
        }
        first, first_decision = controller.try_acquire("user:1", policy)
        second, second_decision = controller.try_acquire("user:2", policy)

        self.assertTrue(first_decision.allowed)
        self.assertIsNotNone(first)
        self.assertFalse(second_decision.allowed)
        self.assertEqual(second_decision.reason, "global_concurrency")
        self.assertIsNone(second)
        first.release()

    def test_rate_window_rejects_without_creating_a_queue(self) -> None:
        controller = QueryAdmissionController()
        policy = {
            "query_rate_limit_enabled": "true",
            "query_rate_limit_window_seconds": "60",
            "query_rate_limit_requests_per_user": "2",
            "query_max_active_requests_per_user": "2",
            "query_max_active_requests": "4",
        }

        leases = []
        for _ in range(2):
            lease, decision = controller.try_acquire("user:1", policy)
            self.assertTrue(decision.allowed)
            leases.append(lease)
        for lease in leases:
            lease.release()
        blocked, decision = controller.try_acquire("user:1", policy)

        self.assertIsNone(blocked)
        self.assertEqual(decision.reason, "rate_limit")
        self.assertGreaterEqual(decision.retry_after_seconds, 1)

    def test_invalid_policy_falls_back_to_safe_bounds(self) -> None:
        policy = normalize_query_protection(
            {
                "query_rate_limit_window_seconds": "-1",
                "query_rate_limit_requests_per_user": "999999",
                "query_max_active_requests_per_user": "999999",
                "query_max_active_requests": "999999",
            }
        )

        self.assertEqual(policy["window_seconds"], 10)
        self.assertEqual(policy["requests_per_user"], 600)
        self.assertEqual(policy["max_active_requests_per_user"], 8)
        self.assertEqual(policy["max_active_requests"], 32)

    def test_concurrent_pressure_never_exceeds_global_admission_limit(self) -> None:
        controller = QueryAdmissionController()
        workers = 128
        policy = {
            "query_rate_limit_enabled": "false",
            "query_max_active_requests_per_user": "1",
            "query_max_active_requests": "8",
        }
        start = Barrier(workers + 1)
        release = Event()
        all_decisions_recorded = Event()
        result_lock = Lock()
        results = []

        def contend(number: int) -> None:
            start.wait(timeout=10)
            lease, decision = controller.try_acquire(f"user:{number}", policy)
            with result_lock:
                results.append((lease, decision))
                if len(results) == workers:
                    all_decisions_recorded.set()
            if lease is not None:
                release.wait(timeout=10)
                lease.release()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(contend, number) for number in range(workers)]
            start.wait(timeout=10)
            self.assertTrue(all_decisions_recorded.wait(timeout=10))
            allowed_count = sum(1 for lease, _decision in results if lease is not None)
            self.assertEqual(allowed_count, 8)
            release.set()
            for future in futures:
                future.result(timeout=10)

        self.assertEqual(controller.status(policy)["active_requests"], 0)


if __name__ == "__main__":
    unittest.main()
