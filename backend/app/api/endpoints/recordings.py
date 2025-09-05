from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
import datetime as dt
from fastapi import Query
from fastapi.responses import FileResponse

from app.services.preflight_service import run_preflight_checks
from app.utils.logging_config import get_logger
from app.services.recording_state_store import recording_state_store
from app.services.recording_service import RecordingStartConfig, start_recording, stop_recording

logger = get_logger(__name__)
router = APIRouter()


class RecordingPreflightResponse(BaseModel):
    has_blackhole: bool
    has_multi_output_device: bool
    default_output_is_multi_output: bool
    microphone_access_granted: bool
    recommendations: list[str]
    transcription_defaults: Optional[dict[str, Any]] = None


@router.api_route("/recordings/preflight", methods=["GET", "POST"], response_model=RecordingPreflightResponse)
async def recordings_preflight():
    """Check whether the system is ready to start a local recording.

    Validates presence of BlackHole, existence of a Multi-Output device, whether
    the default output is Multi-Output, and microphone permission.
    """
    try:
        logger.info("Running recordings preflight checks")
        result = run_preflight_checks()
        # Surface effective transcription defaults from settings
        from app.core.config import settings
        defaults = {
            "whisper_model": settings.WHISPER_MODEL,
            "compute_type": settings.COMPUTE_TYPE,
            "use_diarization": settings.USE_SPEAKER_DIARIZATION,
            "diarization_mode": settings.DIARIZATION_MODE,
            "vad_enabled": getattr(settings, "VAD_ENABLED", True),
            "vad_min_silence_ms": getattr(settings, "VAD_MIN_SILENCE_MS", 300),
            "no_speech_threshold": getattr(settings, "NO_SPEECH_THRESHOLD", 0.3),
            "logprob_threshold": getattr(settings, "LOGPROB_THRESHOLD", -1.0),
        }
        return RecordingPreflightResponse(**result, transcription_defaults=defaults)
    except Exception:
        # Error already logged in the service; expose generic error to client
        raise HTTPException(status_code=500, detail="Error running preflight checks")


class RecordingGlobalStatus(BaseModel):
    state: str  # "idle" | "recording"
    recording_task_id: str | None = None
    elapsed_seconds: float | None = None


@router.get("/recordings/status", response_model=RecordingGlobalStatus)
async def recordings_status() -> RecordingGlobalStatus:
    """Return global recording status for the server.

    - state: "idle" or "recording"
    - recording_task_id: active task id when recording
    - elapsed_seconds: seconds since started_at when recording
    """
    try:
        task = recording_state_store.get_active_task()
    except Exception:
        raise HTTPException(status_code=500, detail="Error reading recording state")

    if not task:
        result = RecordingGlobalStatus(state="idle", recording_task_id=None, elapsed_seconds=None)
        logger.debug("Recording status: idle")
        return result

    # Active only if marked recording and has valid started_at
    if task.status == "recording" and task.started_at is not None:
        try:
            now = dt.datetime.now(dt.timezone.utc)
            started_at = task.started_at
            if started_at.tzinfo is None:
                # Defensive: treat naive as UTC
                logger.warning("Active recording has naive started_at; assuming UTC")
                started_at = started_at.replace(tzinfo=dt.timezone.utc)
            elapsed = (now - started_at).total_seconds()
            if elapsed < 0:
                # Clock skew; clamp to zero and warn
                logger.warning("Active recording started_at is in the future; clamping elapsed to 0")
                elapsed = 0.0
        except Exception:
            raise HTTPException(status_code=500, detail="Error computing elapsed time")

        logger.debug(
            f"Recording status: recording, task_id={task.recording_task_id}, elapsed={elapsed:.3f}s"
        )
        return RecordingGlobalStatus(
            state="recording",
            recording_task_id=task.recording_task_id,
            elapsed_seconds=elapsed,
        )

    # Inconsistent: marked recording but missing started_at
    if task.status == "recording" and task.started_at is None:
        logger.warning("Inconsistent recording task: status=recording but started_at missing; reporting idle")

    # Default to idle for any non-active conditions
    result = RecordingGlobalStatus(state="idle", recording_task_id=None, elapsed_seconds=None)
    logger.debug("Recording status: idle")
    return result


class RecordingStartRequest(BaseModel):
    separate_tracks: bool = True
    create_mixed: bool = True
    sample_rate: int = 48000
    format: str = "wav"


class RecordingStartResponse(BaseModel):
    recording_task_id: str
    status: str
    started_at: str
    config: RecordingStartRequest


@router.post("/recordings/start", response_model=RecordingStartResponse)
async def recordings_start(req: RecordingStartRequest | None = None) -> RecordingStartResponse:
    """Start a new recording if none is active."""
    # Conflict if already active
    try:
        existing = recording_state_store.get_active_task()
    except Exception:
        raise HTTPException(status_code=500, detail="Error reading recording state")

    if existing and existing.status == "recording" and existing.started_at is not None:
        logger.info("Rejecting start: recording already active")
        raise HTTPException(status_code=409, detail="Recording already active")

    cfg = RecordingStartConfig(
        separate_tracks=(req.separate_tracks if req else True),
        create_mixed=(req.create_mixed if req else True),
        sample_rate=(req.sample_rate if req else 48000),
        format=(req.format if req else "wav"),
    )

    try:
        result = await start_recording(cfg)
    except RuntimeError as e:
        if "already active" in str(e).lower():
            raise HTTPException(status_code=409, detail="Recording already active")
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail="Failed to start recording")
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        raise HTTPException(status_code=500, detail="Failed to start recording")

    started_at_str = result.task.started_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    logger.debug(
        f"Start response: task_id={result.task.recording_task_id} started_at={started_at_str}"
    )
    return RecordingStartResponse(
        recording_task_id=result.task.recording_task_id,
        status=result.task.status,
        started_at=started_at_str,
        config=RecordingStartRequest(**cfg.__dict__),
    )


class RecordingStopRequest(BaseModel):
    recording_task_id: str
    auto_handoff: bool = False
    handoff_artifact: str | None = None  # "mixed" | "system" | "mic"


@router.post("/recordings/stop")
async def recordings_stop(req: RecordingStopRequest):
    """Stop the active recording for the given recording_task_id."""
    try:
        result = await stop_recording(
            req.recording_task_id,
            auto_handoff=bool(req.auto_handoff),
            handoff_artifact=(req.handoff_artifact or "mixed"),
        )
        logger.debug(f"Stop response for {req.recording_task_id}: status={result.get('status')}")
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recording task not found or not active")
    except Exception as e:
        logger.error(f"Failed to stop recording {req.recording_task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop recording")


@router.get("/recordings/{recording_task_id}")
async def recordings_detail(recording_task_id: str):
    """Return full details for a recording session, finalized or active."""
    # Prefer finalized
    try:
        finalized = recording_state_store.get_finalized(recording_task_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Error reading recording store")
    if finalized:
        return finalized

    # If active, synthesize a minimal detail view
    try:
        active = recording_state_store.get_active_raw()
    except Exception:
        raise HTTPException(status_code=500, detail="Error reading recording store")
    if active and active.get('recording_task_id') == recording_task_id:
        return {
            'recording_task_id': recording_task_id,
            'status': active.get('status', 'recording'),
            'started_at': active.get('started_at'),
            'completed_at': None,
            'artifacts': { 'mic': None, 'system': None, 'mixed': None },
            'warnings': [],
            'error': None,
            'config': active.get('config'),
            'history': [ { 'state': 'recording', 'at': active.get('started_at') } ],
        }

    raise HTTPException(status_code=404, detail="Recording not found")


@router.get("/recordings/{recording_task_id}/download")
async def recordings_download(recording_task_id: str, artifact: str = Query("best", regex="^(best|mixed|mic|system)$")):
    """Download a finalized recording artifact (mixed|mic|system) for a task.

    Security: serves only files recorded by this server by looking up
    the persisted finalized state and validating existence.
    """
    try:
        finalized = recording_state_store.get_finalized(recording_task_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Error reading recording store")
    if not finalized:
        raise HTTPException(status_code=404, detail="Recording not finalized")

    artifacts = (finalized.get("artifacts") or {})
    if artifact == "best":
        # Prefer mixed, then system, then mic
        for key in ("mixed", "system", "mic"):
            a = artifacts.get(key)
            if a and a.get("path"):
                artifact = key
                art = a
                break
        else:
            raise HTTPException(status_code=404, detail="No available artifact to download")
    else:
        art = artifacts.get(artifact)
    if not art or not art.get("path"):
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact}' not available")
    path = art["path"]
    from pathlib import Path as _P
    p = _P(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    try:
        size = p.stat().st_size
    except Exception:
        size = -1
    logger.info(
        "Download artifact %s for %s -> %s (size=%s)",
        artifact,
        recording_task_id,
        p,
        size,
    )
    # Content type: WAV assumed for now based on pipeline
    return FileResponse(str(p), media_type="audio/wav", filename=f"{recording_task_id}_{artifact}.wav")
