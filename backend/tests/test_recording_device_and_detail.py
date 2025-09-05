import unittest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services import recording_service as rs
from app.api.endpoints.recordings import recordings_start, recordings_detail, RecordingStartRequest
from app.services.recording_state_store import recording_state_store


class TestDeviceResolution(unittest.IsolatedAsyncioTestCase):
    async def test_blackhole_nonzero_index(self):
        fake_list = """
        [AVFoundation input device @ 0xaaa] [0] Built-in Microphone
        [AVFoundation input device @ 0xaaa] [1] USB Mic
        [AVFoundation input device @ 0xaaa] [2] BlackHole 2ch
        """
        with patch("app.services.recording_service._ffmpeg_list_devices_text", return_value=fake_list), \
             patch("app.services.recording_service._spawn_ffmpeg_for_device", new_callable=AsyncMock) as spawn_dev, \
             patch("app.services.recording_service.asyncio.create_subprocess_exec", new_callable=AsyncMock) as spawn_mix, \
             patch("app.services.recording_service.recording_state_store.set_active_task") as set_active:
            # Mock spawned processes to have pids
            class P: 
                def __init__(self, pid): self.pid = pid; self.returncode=None
            spawn_dev.side_effect = [P(11), P(22)]
            async def fake_mix(*args, **kwargs): return P(33)
            spawn_mix.side_effect = fake_mix

            req = RecordingStartRequest(separate_tracks=True, create_mixed=True, sample_rate=48000, format="wav")
            # Start
            with patch("app.api.endpoints.recordings.recording_state_store.get_active_task", return_value=None):
                resp = await recordings_start(req)
            # Ensure device map persisted includes bh index 2
            saved_cfg = set_active.call_args.kwargs.get('config') or {}
            device_map = saved_cfg.get('device_map') or {}
            self.assertEqual(device_map.get('blackhole_index'), 2)


class TestRecordingDetail(unittest.IsolatedAsyncioTestCase):
    async def test_detail_finalized(self):
        payload = {
            'recording_task_id': 'rec-d1',
            'status': 'completed',
            'started_at': '2025-01-01T00:00:00Z',
            'completed_at': '2025-01-01T00:01:00Z',
            'artifacts': { 'mic': None, 'system': None, 'mixed': None },
            'warnings': [], 'error': None
        }
        with patch("app.api.endpoints.recordings.recording_state_store.get_finalized", return_value=payload):
            detail = await recordings_detail('rec-d1')
            self.assertEqual(detail['status'], 'completed')

    async def test_detail_active(self):
        active = {
            'recording_task_id': 'rec-live',
            'status': 'recording',
            'started_at': '2025-01-01T00:00:00Z',
            'config': {'x': 1}
        }
        with patch("app.api.endpoints.recordings.recording_state_store.get_finalized", return_value=None), \
             patch("app.api.endpoints.recordings.recording_state_store.get_active_raw", return_value=active):
            detail = await recordings_detail('rec-live')
            self.assertEqual(detail['status'], 'recording')

