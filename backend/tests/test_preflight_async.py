import unittest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure 'backend' is on sys.path so 'app' package can be imported
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.endpoints.recordings import recordings_preflight


class TestPreflightAsync(unittest.IsolatedAsyncioTestCase):
    async def test_all_good(self):
        with patch("app.services.preflight_service._system_profiler_text", return_value=(
            "Audio:\n  Multi-Output Device\n    Default Output Device: Yes\nInput Devices:\n  BlackHole 2ch\n"
        )), patch("app.services.preflight_service._system_profiler_json", return_value={"ok": True}), \
             patch("app.services.preflight_service._ffmpeg_list_devices", return_value="AVFoundation devices\nBlackHole 2ch"), \
             patch("app.services.preflight_service._ffmpeg_try_capture", return_value=True):
            resp = await recordings_preflight()
            data = resp.model_dump()
            self.assertTrue(data["has_blackhole"])           
            self.assertTrue(data["has_multi_output_device"]) 
            self.assertTrue(data["default_output_is_multi_output"]) 
            self.assertTrue(data["microphone_access_granted"]) 
            self.assertEqual(data["recommendations"], [])

    async def test_missing_blackhole_and_multioutput(self):
        with patch("app.services.preflight_service._system_profiler_text", return_value=(
            "Audio:\n  Built-in Output\n    Default Output Device: Yes\n"
        )), patch("app.services.preflight_service._system_profiler_json", return_value={}), \
             patch("app.services.preflight_service._ffmpeg_list_devices", return_value=""), \
             patch("app.services.preflight_service._ffmpeg_try_capture", return_value=True):
            resp = await recordings_preflight()
            data = resp.model_dump()
            self.assertFalse(data["has_blackhole"])           
            self.assertFalse(data["has_multi_output_device"]) 
            self.assertFalse(data["default_output_is_multi_output"]) 
            self.assertTrue(data["microphone_access_granted"]) 
            recs = data["recommendations"]
            self.assertTrue(any("BlackHole" in r for r in recs))
            self.assertTrue(any("Multi-Output Device" in r for r in recs))

    async def test_microphone_access_denied(self):
        with patch("app.services.preflight_service._system_profiler_text", return_value=(
            "Multi-Output Device\nDefault Output Device: Yes\nBlackHole 2ch\n"
        )), patch("app.services.preflight_service._system_profiler_json", return_value={}), \
             patch("app.services.preflight_service._ffmpeg_list_devices", return_value=""), \
             patch("app.services.preflight_service._ffmpeg_try_capture", return_value=False):
            resp = await recordings_preflight()
            data = resp.model_dump()
            self.assertFalse(data["microphone_access_granted"]) 
            self.assertTrue(any("microphone access" in r.lower() for r in data["recommendations"]))

    async def test_fatal_error(self):
        # Patch the service function used within the endpoint to raise
        with patch("app.services.preflight_service.run_preflight_checks", side_effect=RuntimeError("boom")):
            # The endpoint raises HTTPException(500); emulate FastAPI response by catching
            try:
                await recordings_preflight()
            except Exception as e:
                self.assertEqual(getattr(e, "status_code", None), 500)
                self.assertEqual(getattr(e, "detail", None), "Error running preflight checks")


if __name__ == "__main__":
    asyncio.run(unittest.main())
