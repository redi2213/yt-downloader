import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import run_labels  # noqa: E402


def _job(status, *steps):
    return {"status": status, "steps": [{"status": s, "name": f"s{i + 1}"} for i, s in enumerate(steps)]}


class ProgressSummaryTest(unittest.TestCase):
    def test_nothing_running(self):
        self.assertIsNone(run_labels.progress_summary([_job("completed", "completed")]))
        self.assertIsNone(run_labels.progress_summary([]))

    def test_waiting_for_runner(self):
        self.assertEqual(run_labels.progress_summary([_job("queued")]), {"waiting": True})

    def test_step_in_progress(self):
        job = _job("in_progress", "completed", "completed", "completed", "in_progress", "pending")
        self.assertEqual(run_labels.progress_summary([job]), {"step": 4, "total": 5, "name": "s4"})

    def test_between_steps(self):
        job = _job("in_progress", "completed", "pending")
        self.assertEqual(run_labels.progress_summary([job]), {"step": 2, "total": 2, "name": ""})


if __name__ == "__main__":
    unittest.main()
