import unittest
import asyncio
import sys
from datetime import timezone, datetime
from pathlib import Path
from unittest.mock import patch

# Ensure 'backend' is on sys.path so 'app' package can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.endpoints.recordings import recordings_status
from app.services.recording_state_store import RecordingTask


class TestRecordingStatus(unittest.IsolatedAsyncioTestCase):
    async def test_status_idle(self):
        # No active task
        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=None):
            resp = await recordings_status()
            data = resp.model_dump()
            self.assertEqual(data["state"], "idle")
            self.assertIsNone(data["recording_task_id"])
            self.assertIsNone(data["elapsed_seconds"])

    async def test_status_active_elapsed(self):
        # Active task with known start time
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        task = RecordingTask(recording_task_id="rec-12345", status="recording", started_at=start)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2025, 1, 1, 12, 1, 27, 300000, tzinfo=timezone.utc)

        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=task), \
             patch("app.api.endpoints.recordings.dt.datetime", FixedDatetime):
            resp = await recordings_status()
            data = resp.model_dump()
            self.assertEqual(data["state"], "recording")
            self.assertEqual(data["recording_task_id"], "rec-12345")
            # 87.3 seconds elapsed
            self.assertAlmostEqual(float(data["elapsed_seconds"]), 87.3, places=3)

    async def test_inconsistent_missing_started_at(self):
        # Marked recording but missing started_at -> idle and warning logged
        task = RecordingTask(recording_task_id="rec-x", status="recording", started_at=None)
        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=task), \
             patch("app.api.endpoints.recordings.logger.warning") as warn_mock:
            resp = await recordings_status()
            data = resp.model_dump()
            self.assertEqual(data["state"], "idle")
            self.assertTrue(warn_mock.called)

    async def test_persistence_across_restart(self):
        # Simulates reading persisted active task after restart
        start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        task = RecordingTask(recording_task_id="rec-persist", status="recording", started_at=start)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2025, 1, 1, 0, 0, 10, tzinfo=timezone.utc)

        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=task), \
             patch("app.api.endpoints.recordings.dt.datetime", FixedDatetime):
            resp = await recordings_status()
            data = resp.model_dump()
            self.assertEqual(data["state"], "recording")
            self.assertEqual(data["recording_task_id"], "rec-persist")
            self.assertAlmostEqual(float(data["elapsed_seconds"]), 10.0, places=3)

    async def test_store_read_error_returns_500(self):
        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", side_effect=RuntimeError("boom")):
            try:
                await recordings_status()
            except Exception as e:
                self.assertEqual(getattr(e, "status_code", None), 500)
                self.assertEqual(getattr(e, "detail", None), "Error reading recording state")


if __name__ == "__main__":
    asyncio.run(unittest.main())

