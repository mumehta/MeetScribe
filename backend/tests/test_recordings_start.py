import unittest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Ensure 'backend' is on sys.path so 'app' package can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.endpoints.recordings import recordings_start, RecordingStartRequest
from app.services.recording_state_store import RecordingTask


class TestRecordingStart(unittest.IsolatedAsyncioTestCase):
    async def test_start_success(self):
        # No active task; start should succeed
        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=None), \
             patch("app.api.endpoints.recordings.start_recording", new_callable=AsyncMock) as start_mock:
            # Mock result
            task = RecordingTask(recording_task_id="rec-abc", status="recording", started_at=None)
            # Provide started_at via start_mock return
            from datetime import datetime, timezone
            task.started_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            class Result:
                def __init__(self, task):
                    self.task = task
                    self.config = None
                    self.output_dir = Path("/tmp")
            start_mock.return_value = Result(task)

            resp = await recordings_start(RecordingStartRequest())
            data = resp.model_dump()
            self.assertEqual(data["status"], "recording")
            self.assertEqual(data["recording_task_id"], "rec-abc")
            self.assertTrue(data["started_at"].endswith("Z"))

    async def test_start_conflict(self):
        from datetime import datetime, timezone
        active = RecordingTask(recording_task_id="rec-live", status="recording", started_at=datetime.now(timezone.utc))
        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=active):
            try:
                await recordings_start(RecordingStartRequest())
            except Exception as e:
                self.assertEqual(getattr(e, "status_code", None), 409)
                self.assertEqual(getattr(e, "detail", None), "Recording already active")

    async def test_start_failure(self):
        # Simulate failure during starting processes
        with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=None), \
             patch("app.api.endpoints.recordings.start_recording", new_callable=AsyncMock, side_effect=RuntimeError("spawn failed")):
            try:
                await recordings_start(RecordingStartRequest())
            except Exception as e:
                self.assertEqual(getattr(e, "status_code", None), 500)
                self.assertEqual(getattr(e, "detail", None), "Failed to start recording")


if __name__ == "__main__":
    asyncio.run(unittest.main())

