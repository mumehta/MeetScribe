import asyncio
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import os
import signal
import subprocess
import json

from app.core.config import settings
from app.utils.logging_config import get_logger
from app.services.recording_state_store import RecordingTask, recording_state_store
from app.services.audio_processing_service import audio_processing_service


logger = get_logger(__name__)


@dataclass
class RecordingStartConfig:
    separate_tracks: bool = True
    create_mixed: bool = True
    sample_rate: int = 48000
    format: str = "wav"


@dataclass
class RecordingStartResult:
    task: RecordingTask
    config: RecordingStartConfig
    output_dir: Path


async def _spawn_ffmpeg_for_device(device_spec: str, sample_rate: int, out_file: Path) -> asyncio.subprocess.Process:
    """Spawn ffmpeg to capture audio from a given avfoundation device spec.

    device_spec examples:
      - ":0" (default input)
      - ":1" (specific input index)
    """
    cmd = [
        "ffmpeg",
        "-hide_banner", "-nostats", "-loglevel", "error", "-nostdin", "-y",
        "-thread_queue_size", "4096",
        "-f", "avfoundation",
        "-i", device_spec,
        "-ac", "1",
        "-ar", str(sample_rate),
        str(out_file),
    ]
    logger.debug(f"Spawning ffmpeg: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Quick health check: if ffmpeg exits immediately, surface the error
    try:
        await asyncio.sleep(0.3)
        if proc.returncode is not None:
            _out, err = await proc.communicate()
            err_text = (err or b"").decode("utf-8", "ignore")
            logger.error(f"ffmpeg exited immediately for device {device_spec}: rc={proc.returncode} err={err_text}")
            raise RuntimeError(f"ffmpeg failed to open device {device_spec}: rc={proc.returncode}")
    except Exception:
        # Re-raise to let caller handle; ensures start_recording reports failure clearly
        raise
    return proc


async def _drain_stream_to_file(stream: asyncio.StreamReader, log_path: Path):
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab", buffering=0) as f:
            while True:
                chunk = await stream.read(1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception:
        pass


def _ffmpeg_list_devices_text() -> str:
    try:
        # ffmpeg prints device list to stderr for -list_devices
        proc = subprocess.run(
            ['ffmpeg', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        # Combine to make parsing resilient
        return (proc.stdout or '') + "\n" + (proc.stderr or '')
    except Exception as e:
        logger.error(f"Failed to enumerate avfoundation devices: {e}")
        return ""


def _system_profiler_text() -> str:
    try:
        proc = subprocess.run(
            ["system_profiler", "SPAudioDataType"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=6,
        )
        return (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr and not proc.stdout else "")
    except Exception:
        return ""


def _detect_default_input_device_name(text: str) -> Optional[str]:
    """Parse system_profiler text to find the device whose 'Default Input Device' is Yes.

    Heuristic similar to preflight parsing: track the current device name and
    return it when 'Default Input Device: Yes' appears within that section.
    """
    if not text:
        return None
    current_name = None
    for raw in text.splitlines():
        line = raw.strip()
        # A crude way to capture device headers vs key:value lines
        if line and ":" not in line:
            current_name = line
        if line.lower().startswith("default input device:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in {"yes", "true"}:
                return current_name
    return None


def _resolve_devices(blackhole_name: str) -> dict:
    """Resolve avfoundation indices for BlackHole and default mic.

    Returns a dict with {blackhole_index, mic_index, device_names}.
    Raises RuntimeError if BlackHole cannot be found.
    """
    text = _ffmpeg_list_devices_text()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    inputs: dict[int, str] = {}
    in_audio_section = False
    for ln in lines:
        if 'AVFoundation input device' in ln or 'AVFoundation audio devices' in ln or 'Input Devices' in ln:
            in_audio_section = True
        # Typical lines: [AVFoundation input device @ 0x...] [0] Built-in Microphone
        if in_audio_section:
            # Extract index and name heuristically
            # Try [0] Name pattern
            if ln.startswith('[') and '] ' in ln:
                try:
                    idx_part = ln.split(']')[1].strip()
                    if idx_part and idx_part[0].isdigit():
                        idx = int(idx_part.split(']')[0])  # fallback; rarely used
                except Exception:
                    idx = None
            # Simpler robust parse: find patterns like "] 0]" or "] [0]"
            idx = None
            name = None
            # Look for [...] [N] Device Name
            if '] [' in ln and '] ' in ln:
                try:
                    after = ln.split('] [', 1)[1]
                    idx = int(after.split(']')[0])
                    name = after.split(']')[-1].strip()
                except Exception:
                    pass
            # Fallback pattern: [N] Name
            if idx is None and ln.startswith('['):
                try:
                    idx = int(ln.split(']')[0].lstrip('['))
                    name = ln.split(']')[-1].strip()
                except Exception:
                    pass
            if idx is not None and name:
                inputs[idx] = name

    # Resolve BlackHole by name
    bh_index = None
    for i, n in inputs.items():
        if blackhole_name.lower() in n.lower():
            bh_index = i
            break
    if bh_index is None:
        raise RuntimeError(f"BlackHole device '{blackhole_name}' not found in avfoundation inputs")

    # Build candidates excluding BlackHole and any ignored patterns
    ignore_tokens = [t.strip().lower() for t in (settings.RECORDING_IGNORE_INPUTS or "").split(",") if t.strip()]
    def not_ignored(name: str) -> bool:
        low = name.lower()
        return not any(tok in low for tok in ignore_tokens)

    candidates = {i: n for i, n in inputs.items() if i != bh_index and not_ignored(n)}

    # 1) Try system default input from system_profiler
    mic_index = None
    try:
        sp_name = _detect_default_input_device_name(_system_profiler_text())
        if sp_name:
            for i, n in candidates.items():
                if sp_name.lower() in n.lower() or n.lower() in sp_name.lower():
                    mic_index = i
                    break
    except Exception:
        pass

    # 2) Apply configurable name hint
    if mic_index is None and settings.RECORDING_MIC_NAME_HINT:
        hint = settings.RECORDING_MIC_NAME_HINT.lower()
        for i, n in candidates.items():
            if hint in n.lower():
                mic_index = i
                break

    # 3) Heuristic preference list
    if mic_index is None:
        preferred_labels = [
            "MacBook Pro Microphone",
            "Built-in Microphone",
            "Internal Microphone",
            "Microphone",
        ]
        for label in preferred_labels:
            for i, n in candidates.items():
                if label.lower() in n.lower():
                    mic_index = i
                    break
            if mic_index is not None:
                break

    # 4) Fallback: lowest index among candidates; final fallback 0
    if mic_index is None and candidates:
        mic_index = sorted(candidates.keys())[0]
    if mic_index is None:
        mic_index = 0

    logger.debug(
        f"Resolved AVFoundation inputs: {inputs}; ignored={ignore_tokens}; chosen bh_index={bh_index}, mic_index={mic_index} ({inputs.get(mic_index)})"
    )

    return {
        'blackhole_index': bh_index,
        'mic_index': mic_index,
        'device_names': inputs,
    }


async def start_recording(config: Optional[RecordingStartConfig] = None) -> RecordingStartResult:
    """Start a new recording session.

    - Ensures no other active recording is running.
    - Spawns ffmpeg processes for mic and system (BlackHole) capture.
    - Persists active recording state.
    """
    cfg = config or RecordingStartConfig()

    # Single-active-recording guard
    active = recording_state_store.get_active_task()
    if active and active.status == "recording" and active.started_at is not None:
        raise RuntimeError("Recording already active")

    # Create new task id and directory
    task_id = f"rec-{uuid.uuid4().hex}"
    out_dir = settings.workspace_root_path / "recordings" / task_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Output files
    mic_file = out_dir / f"mic.{cfg.format}"
    sys_file = out_dir / f"system.{cfg.format}"
    mixed_file = out_dir / f"mixed.{cfg.format}"

    # Start capture processes in background (do not await completion)
    try:
        # Resolve device indices
        device_map = _resolve_devices(settings.BLACKHOLE_DEVICE_NAME)
        mic_idx = device_map['mic_index']
        bh_idx = device_map['blackhole_index']
        # Allow explicit index overrides from settings/.env
        if settings.RECORDING_MIC_INDEX is not None:
            mic_idx = int(settings.RECORDING_MIC_INDEX)
        if settings.RECORDING_BLACKHOLE_INDEX is not None:
            bh_idx = int(settings.RECORDING_BLACKHOLE_INDEX)
        logger.info(
            "Recording device map resolved: mic_idx=%s(%s) bh_idx=%s(%s)",
            mic_idx,
            device_map['device_names'].get(mic_idx),
            bh_idx,
            device_map['device_names'].get(bh_idx),
        )

        mic_proc = await _spawn_ffmpeg_for_device(f":{mic_idx}", cfg.sample_rate, mic_file)
        sys_proc = await _spawn_ffmpeg_for_device(f":{bh_idx}", cfg.sample_rate, sys_file)
        logger.info(
            "Spawned ffmpeg processes: mic_pid=%s sys_pid=%s out_dir=%s",
            getattr(mic_proc, 'pid', None),
            getattr(sys_proc, 'pid', None),
            out_dir,
        )
        # Prepare log files and drain stderr to diagnose device errors
        (out_dir / "mic.ffmpeg.log").touch(exist_ok=True)
        (out_dir / "system.ffmpeg.log").touch(exist_ok=True)
        asyncio.create_task(_drain_stream_to_file(mic_proc.stderr, out_dir / "mic.ffmpeg.log"))
        asyncio.create_task(_drain_stream_to_file(sys_proc.stderr, out_dir / "system.ffmpeg.log"))

        # Optionally create mixed track by launching a combiner ffmpeg that maps
        # channels. If configured, run a live mixing pipeline capturing both devices.
        mix_proc = None
        if cfg.create_mixed and settings.RECORDING_USE_LIVE_MIX:
            # Build filter depending on policy
            if settings.RECORDING_MIX_POLICY == 'audible_mix':
                # -3dB each then amix
                filtergraph = '[0:a]volume=0.707[a0];[1:a]volume=0.707[a1];[a0][a1]amix=inputs=2:duration=longest[a]'
                map_args = ['-map', '[a]', '-ac', '2']
            else:
                # separation: force mono then join as stereo L/R
                filtergraph = '[0:a]aformat=channel_layouts=mono[a0];[1:a]aformat=channel_layouts=mono[a1];[a0][a1]join=inputs=2:channel_layout=stereo[a]'
                map_args = ['-map', '[a]']
            cmd = [
                'ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'error', '-nostdin', '-y',
                '-thread_queue_size', '4096', '-f', 'avfoundation', '-i', f":{mic_idx}",
                '-thread_queue_size', '4096', '-f', 'avfoundation', '-i', f":{bh_idx}",
                '-filter_complex', filtergraph,
                *map_args,
                '-ar', str(cfg.sample_rate),
                str(mixed_file)
            ]
            logger.debug(f"Spawning live mix ffmpeg: {' '.join(cmd)}")
            mix_proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            (out_dir / "mixed.ffmpeg.log").touch(exist_ok=True)
            asyncio.create_task(_drain_stream_to_file(mix_proc.stderr, out_dir / "mixed.ffmpeg.log"))

    except Exception as e:
        logger.error(f"Failed to start recording processes: {e}")
        # Best effort: terminate any started processes
        try:
            if 'mic_proc' in locals() and mic_proc.returncode is None:
                mic_proc.terminate()
        except Exception:
            pass
        try:
            if 'sys_proc' in locals() and sys_proc.returncode is None:
                sys_proc.terminate()
        except Exception:
            pass
        try:
            if 'mix_proc' in locals() and mix_proc and mix_proc.returncode is None:
                mix_proc.terminate()
        except Exception:
            pass
        raise

    # Persist active task state
    started_at = datetime.now(timezone.utc)
    task = RecordingTask(recording_task_id=task_id, status="recording", started_at=started_at)
    pids = {
        "mic": getattr(mic_proc, "pid", None),
        "system": getattr(sys_proc, "pid", None),
        "mix": getattr(locals().get('mix_proc'), 'pid', None) if 'mix_proc' in locals() else None,
    }
    config_payload = asdict(cfg)
    try:
        config_payload['device_map'] = {
            'blackhole_index': bh_idx,
            'mic_index': mic_idx,
            'device_names': device_map['device_names'],
        }
    except Exception:
        pass
    recording_state_store.set_active_task(task, config=config_payload, pids=pids, output_dir=out_dir)

    logger.info(
        f"Recording started task_id={task_id} sample_rate={cfg.sample_rate} format={cfg.format} "
        f"out_dir={out_dir} mic_file={mic_file} system_file={sys_file} pids={pids} "
        f"device_map={{'bh': {config_payload.get('device_map', {}).get('blackhole_index')}, 'mic': {config_payload.get('device_map', {}).get('mic_index')}}}"
    )

    return RecordingStartResult(task=task, config=cfg, output_dir=out_dir)


async def _wait_process_exit(pid: int, timeout: float) -> bool:
    """Wait until a process with pid disappears, up to timeout seconds."""
    end = asyncio.get_event_loop().time() + timeout
    while True:
        try:
            os.kill(pid, 0)
            # Still alive
            if asyncio.get_event_loop().time() >= end:
                return False
            await asyncio.sleep(0.2)
        except OSError:
            return True


async def _ffprobe_metadata(file_path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(file_path.resolve()),
        "duration_seconds": None,
        "sample_rate": None,
        "channels": None,
        "size_bytes": None,
    }
    try:
        if file_path.exists():
            info["size_bytes"] = file_path.stat().st_size
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe = json.loads(result.stdout or '{}')
        if 'format' in probe:
            fmt = probe['format']
            if 'duration' in fmt:
                info['duration_seconds'] = float(fmt['duration'])
        streams = [s for s in probe.get('streams', []) if s.get('codec_type') == 'audio']
        if streams:
            s = streams[0]
            if 'sample_rate' in s:
                try:
                    info['sample_rate'] = int(s['sample_rate'])
                except Exception:
                    pass
            if 'channels' in s:
                info['channels'] = int(s['channels'])
    except Exception as e:
        logger.warning(f"ffprobe failed for {file_path}: {e}")
    return info


async def _generate_mixed_if_requested(out_dir: Path, cfg: RecordingStartConfig) -> Optional[Path]:
    if not cfg.create_mixed:
        return None
    mic = out_dir / f"mic.{cfg.format}"
    sysf = out_dir / f"system.{cfg.format}"
    mixed = out_dir / f"mixed.{cfg.format}"
    if not (mic.exists() and sysf.exists()):
        return None
    try:
        # Build filtergraph depending on policy
        if settings.RECORDING_MIX_POLICY == 'audible_mix':
            filtergraph = '[0:a]volume=0.707[a0];[1:a]volume=0.707[a1];[a0][a1]amix=inputs=2:duration=longest[a]'
            map_args = ['-map', '[a]', '-ac', '2']
        else:
            filtergraph = '[0:a]aformat=channel_layouts=mono[a0];[1:a]aformat=channel_layouts=mono[a1];[a0][a1]join=inputs=2:channel_layout=stereo[a]'
            map_args = ['-map', '[a]']
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', str(mic), '-i', str(sysf),
            '-filter_complex', filtergraph,
            *map_args,
            str(mixed)
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _out, err = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(f"Failed to create mixed track: rc={proc.returncode} err={(err or b'').decode('utf-8', 'ignore')}")
            return None
        return mixed if mixed.exists() else None
    except Exception as e:
        logger.warning(f"Exception while creating mixed track: {e}")
        return None


async def stop_recording(recording_task_id: str, *, auto_handoff: bool, handoff_artifact: str) -> dict:
    """Stop active recording and finalize artifacts. Returns response payload."""
    # Idempotency: if already finalized, return saved payload
    finalized = recording_state_store.get_finalized(recording_task_id)
    if finalized:
        return finalized

    active_raw = recording_state_store.get_active_raw()
    if not active_raw or active_raw.get('recording_task_id') != recording_task_id or active_raw.get('status') != 'recording':
        # If not active and no finalized record, treat as not found
        raise FileNotFoundError("Recording task not active")

    cfg_dict = active_raw.get('config') or {}
    cfg = RecordingStartConfig(
        separate_tracks=bool(cfg_dict.get('separate_tracks', True)),
        create_mixed=bool(cfg_dict.get('create_mixed', True)),
        sample_rate=int(cfg_dict.get('sample_rate', 48000)),
        format=str(cfg_dict.get('format', 'wav')),
    )
    out_dir = Path(active_raw.get('output_dir') or (settings.intermediate_folder_path / recording_task_id))
    pids = active_raw.get('pids') or {}
    logger.info(
        "Stopping recording task_id=%s out_dir=%s pids=%s cfg=%s",
        recording_task_id,
        out_dir,
        pids,
        cfg,
    )

    warnings = []
    # Stop processes gracefully
    for name in ('mic', 'system', 'mix'):
        pid = pids.get(name)
        if not pid:
            continue
        try:
            os.kill(pid, signal.SIGINT)
            ok = await _wait_process_exit(pid, timeout=5.0)
            if not ok:
                logger.warning(f"Process {name} pid={pid} did not exit on SIGINT; sending SIGTERM")
                warnings.append(f"{name}_terminate_timeout")
                os.kill(pid, signal.SIGTERM)
                await _wait_process_exit(pid, timeout=2.0)
        except ProcessLookupError:
            # Already gone
            pass
        except Exception as e:
            logger.warning(f"Failed to stop {name} pid={pid}: {e}")
            warnings.append(f"{name}_stop_error")

    # Optionally generate mixed track
    mixed_path = await _generate_mixed_if_requested(out_dir, cfg)

    # Probe artifacts
    artifacts: Dict[str, Optional[Dict[str, Any]]] = {"mic": None, "system": None, "mixed": None}
    mic_file = out_dir / f"mic.{cfg.format}"
    sys_file = out_dir / f"system.{cfg.format}"
    logger.debug("Checking artifact existence: mic=%s system=%s mixed(expected)=%s",
                 mic_file.exists(), sys_file.exists(), (out_dir / f"mixed.{cfg.format}").exists())
    if mic_file.exists():
        artifacts['mic'] = await _ffprobe_metadata(mic_file)
    else:
        warnings.append("mic_missing")
    if sys_file.exists():
        artifacts['system'] = await _ffprobe_metadata(sys_file)
    else:
        warnings.append("system_missing")
    if mixed_path and mixed_path.exists():
        artifacts['mixed'] = await _ffprobe_metadata(mixed_path)
    elif cfg.create_mixed:
        warnings.append("mixed_missing")

    # Duration mismatch warning if both tracks present
    try:
        d_mic = (artifacts['mic'] or {}).get('duration_seconds') or 0
        d_sys = (artifacts['system'] or {}).get('duration_seconds') or 0
        if d_mic and d_sys and abs(float(d_mic) - float(d_sys)) > 2.0:
            warnings.append('duration_mismatch')
    except Exception:
        pass

    # Determine status
    status = 'completed'
    error_msg = None
    if not artifacts['mic'] and not artifacts['system']:
        status = 'error'
        error_msg = 'no_artifacts_created'

    completed_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # Auto-handoff
    auto_handoff_result = None
    if auto_handoff:
        # Choose artifact in preference order
        preferred = [handoff_artifact, 'mixed', 'system', 'mic']
        chosen = None
        for k in preferred:
            a = artifacts.get(k)
            if a and a.get('path') and Path(a['path']).exists() and (a.get('size_bytes') or 0) > 0:
                chosen = a['path']
                chosen_key = k
                break
        if chosen:
            try:
                proc_task_id = await audio_processing_service.create_processing_task(
                    chosen,
                    original_filename=Path(chosen).name,
                    input_type="server_local",
                    provenance={"source": "recording", "recording_task_id": recording_task_id},
                )
                # Kick off background processing
                asyncio.create_task(audio_processing_service.process_audio_file(proc_task_id))
                auto_handoff_result = {
                    "started": True,
                    "processing_task_id": proc_task_id,
                    "message": f"Registered server-local file for processing ({chosen_key})",
                }
            except Exception as e:
                logger.error(f"Auto-handoff failed: {e}")
                auto_handoff_result = {
                    "started": False,
                    "processing_task_id": None,
                    "message": f"Auto-handoff failed: {e}",
                }
        else:
            auto_handoff_result = {
                "started": False,
                "processing_task_id": None,
                "message": "No suitable artifact available for handoff",
            }

    resp = {
        "recording_task_id": recording_task_id,
        "status": status,
        "completed_at": completed_at,
        "artifacts": artifacts,
        "auto_handoff_result": auto_handoff_result,
        "warnings": warnings,
        "error": error_msg,
    }

    # Persist finalized and clear active
    try:
        recording_state_store.save_finalized(recording_task_id, resp)
    except Exception as e:
        logger.error(f"Failed to persist finalized recording: {e}")
        # Do not fail the response; endpoint should be reliable

    logger.info(
        f"Recording stopped task_id={recording_task_id} status={status} warnings={warnings} out_dir={out_dir}"
    )
    return resp
