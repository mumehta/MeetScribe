from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal

from app.core.config import settings
from app.utils.logging_config import get_logger


logger = get_logger(__name__)


RecordingStatus = Literal[
    "preflight", "recording", "finalizing", "completed", "error"
]


@dataclass
class RecordingTask:
    recording_task_id: str
    status: RecordingStatus
    started_at: Optional[datetime]

    @staticmethod
    def from_dict(data: dict) -> "RecordingTask":
        started_at_raw = data.get("started_at")
        started_at_dt: Optional[datetime] = None
        if started_at_raw:
            try:
                # Accept RFC3339/ISO8601. Ensure timezone-aware; assume UTC if 'Z'.
                if isinstance(started_at_raw, str):
                    if started_at_raw.endswith("Z"):
                        started_at_raw = started_at_raw.replace("Z", "+00:00")
                    started_at_dt = datetime.fromisoformat(started_at_raw)
                    if started_at_dt.tzinfo is None:
                        # Treat naive as UTC to avoid exceptions; log warning
                        logger.warning("RecordingTask.started_at is naive; assuming UTC")
                        started_at_dt = started_at_dt.replace(tzinfo=timezone.utc)
                elif isinstance(started_at_raw, (int, float)):
                    started_at_dt = datetime.fromtimestamp(float(started_at_raw), tz=timezone.utc)
            except Exception:
                logger.warning("Failed to parse started_at; treating as missing")
                started_at_dt = None

        return RecordingTask(
            recording_task_id=data.get("recording_task_id", ""),
            status=data.get("status", "error"),
            started_at=started_at_dt,
        )


class RecordingStateStore:
    """File-backed global recording state store.

    This is designed to be the single source of truth for whether a recording
    is currently active. It uses a small JSON file under the project's
    intermediate folder to ensure durability across process restarts.
    """

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.state_file = state_file or (settings.intermediate_folder_path / "recording_state.json")
        # Ensure directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            with self.state_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            # Bubble up; API layer will convert to 500
            logger.error(f"Failed to read recording state file: {e}")
            raise

    def _write_state(self, state: dict) -> None:
        try:
            tmp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            tmp.replace(self.state_file)
        except Exception as e:
            logger.error(f"Failed to write recording state file: {e}")
            raise

    def get_active_task(self) -> Optional[RecordingTask]:
        """Return the active recording task if present and marked active.

        The JSON structure is expected to be:
        {
          "active_recording": {
            "recording_task_id": "rec-...",
            "status": "recording",
            "started_at": "2025-01-01T12:00:00Z"
          }
        }
        """
        state = self._read_state()
        active = state.get("active_recording")
        if not active or not isinstance(active, dict):
            return None
        task = RecordingTask.from_dict(active)
        return task

    def get_active_raw(self) -> Optional[dict]:
        state = self._read_state()
        active = state.get("active_recording")
        return active if isinstance(active, dict) else None

    def set_active_task(self, task: RecordingTask, config: Optional[dict] = None, *, pids: Optional[dict] = None, output_dir: Optional[Path] = None) -> None:
        payload = {
            "active_recording": {
                "recording_task_id": task.recording_task_id,
                "status": task.status,
                # Store in RFC3339 with Z
                "started_at": task.started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if task.started_at else None,
                "config": config or {},
                "pids": pids or {},
                "output_dir": str(output_dir) if output_dir else None,
            }
        }
        self._write_state(payload)

    def clear_active(self) -> None:
        state = self._read_state()
        if "active_recording" in state:
            state.pop("active_recording", None)
            self._write_state(state)

    # Finalized tasks persistence (for idempotent stop responses)
    def save_finalized(self, recording_task_id: str, response_payload: dict) -> None:
        state = self._read_state()
        tasks = state.get("finalized_tasks") or {}
        tasks[recording_task_id] = response_payload
        state["finalized_tasks"] = tasks
        # Also clear active if it matches
        active = state.get("active_recording", {})
        if active.get("recording_task_id") == recording_task_id:
            state.pop("active_recording", None)
        self._write_state(state)

    def get_finalized(self, recording_task_id: str) -> Optional[dict]:
        state = self._read_state()
        tasks = state.get("finalized_tasks") or {}
        return tasks.get(recording_task_id)


# Provide a module-level default store instance for app usage
recording_state_store = RecordingStateStore()
