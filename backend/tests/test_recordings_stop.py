import unittest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Ensure 'backend' is on sys.path so 'app' package can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.endpoints.recordings import recordings_stop, RecordingStopRequest
from app.services import recording_service as rs


class TestRecordingStopEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_stop_success_no_handoff(self):
        payload = {
            "recording_task_id": "rec-xyz",
            "status": "completed",
            "completed_at": "2025-01-01T00:00:10Z",
            "artifacts": {"mic": None, "system": None, "mixed": None},
            "auto_handoff_result": None,
            "warnings": [],
            "error": None,
        }
        with patch("app.api.endpoints.recordings.stop_recording", new_callable=AsyncMock, return_value=payload):
            resp = await recordings_stop(RecordingStopRequest(recording_task_id="rec-xyz", auto_handoff=False))
            self.assertEqual(resp["status"], "completed")
            self.assertEqual(resp["recording_task_id"], "rec-xyz")

    async def test_stop_not_found(self):
        with patch("app.api.endpoints.recordings.stop_recording", new_callable=AsyncMock, side_effect=FileNotFoundError()):
            try:
                await recordings_stop(RecordingStopRequest(recording_task_id="rec-missing", auto_handoff=False))
            except Exception as e:
                self.assertEqual(getattr(e, "status_code", None), 404)

    async def test_stop_auto_handoff(self):
        payload = {
            "recording_task_id": "rec-xyz",
            "status": "completed",
            "completed_at": "2025-01-01T00:00:10Z",
            "artifacts": {"mic": None, "system": None, "mixed": {"path": "/a/mixed.wav", "size_bytes": 10}},
            "auto_handoff_result": {"started": True, "processing_task_id": "proc-1", "message": "ok"},
            "warnings": [],
            "error": None,
        }
        with patch("app.api.endpoints.recordings.stop_recording", new_callable=AsyncMock, return_value=payload):
            resp = await recordings_stop(RecordingStopRequest(recording_task_id="rec-xyz", auto_handoff=True))
            self.assertTrue(resp["auto_handoff_result"]["started"]) 


class TestRecordingStopService(unittest.IsolatedAsyncioTestCase):
    async def test_service_stop_timeout_warning_and_metadata(self):
        # Mock active state
        active_raw = {
            "recording_task_id": "rec-1",
            "status": "recording",
            "started_at": "2025-01-01T00:00:00Z",
            "config": {"create_mixed": False, "format": "wav", "sample_rate": 48000, "separate_tracks": True},
            "pids": {"mic": 111, "system": 222},
            "output_dir": str(Path("backend/intermediate/rec-1").resolve()),
        }

        # Ensure expected files exist conditions (mock fs and probe)
        with \
             patch("app.services.recording_service.recording_state_store.get_finalized", return_value=None), \
             patch("app.services.recording_service.recording_state_store.get_active_raw", return_value=active_raw), \
             patch("app.services.recording_service.os.kill") as kill_mock, \
             patch("app.services.recording_service._wait_process_exit", new_callable=AsyncMock, side_effect=[False, True, True]), \
             patch("app.services.recording_service._ffprobe_metadata", new_callable=AsyncMock, return_value={"path": "/p.wav", "duration_seconds": 1.0, "sample_rate": 48000, "channels": 2, "size_bytes": 100}), \
             patch("app.services.recording_service.Path.exists", return_value=True), \
             patch("app.services.recording_service.Path.stat", return_value=type("S", (), {"st_size": 100})()), \
             patch("app.services.recording_service.recording_state_store.save_finalized") as save_mock:
            resp = await rs.stop_recording("rec-1", auto_handoff=False, handoff_artifact="mixed")
            self.assertEqual(resp["status"], "completed")
            self.assertIn("mic", resp["artifacts"])  
            self.assertTrue(any("terminate_timeout" in w for w in resp["warnings"]))
            self.assertTrue(save_mock.called)


if __name__ == "__main__":
    asyncio.run(unittest.main())
