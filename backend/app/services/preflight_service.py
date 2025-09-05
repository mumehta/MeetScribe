import json
import subprocess
import shlex
from typing import Dict, Tuple

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def _run_command(cmd: str, timeout: int = 8) -> Tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    logger.debug(f"Running command: {cmd}")
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        logger.warning(f"Command timed out: {cmd}")
        return 124, "", str(e)
    except Exception as e:
        logger.error(f"Command failed to start: {cmd} - {e}", exc_info=True)
        return 1, "", str(e)


def _system_profiler_text() -> str:
    """Get textual audio device info from system_profiler (macOS)."""
    rc, out, err = _run_command("system_profiler SPAudioDataType")
    if rc != 0:
        logger.debug(f"system_profiler text rc={rc}, err={err}")
    return out + ("\n" + err if err and not out else "")


def _system_profiler_json() -> Dict:
    """Get JSON audio device info from system_profiler (macOS)."""
    rc, out, err = _run_command("system_profiler SPAudioDataType -json")
    if rc != 0:
        logger.debug(f"system_profiler json rc={rc}, err={err}")
        return {}
    try:
        return json.loads(out or "{}")
    except Exception:
        logger.debug("Failed to parse system_profiler JSON output")
        return {}


def _ffmpeg_list_devices() -> str:
    """List AVFoundation devices via ffmpeg."""
    # ffmpeg prints device list to stderr for -list_devices
    rc, out, err = _run_command('ffmpeg -f avfoundation -list_devices true -i ""')
    text = (out or "") + ("\n" + err if err else "")
    if rc != 0:
        logger.debug(f"ffmpeg -list_devices rc={rc}")
    return text


def _ffmpeg_try_capture() -> bool:
    """Attempt a very short capture from default input to infer mic permission."""
    # Capture 0.1s from default input (index 0) to null sink.
    # Using low loglevel + no stdin to avoid hangs.
    cmd = 'ffmpeg -hide_banner -nostats -loglevel error -nostdin -f avfoundation -i ":0" -t 0.1 -ac 1 -f null -'
    rc, out, err = _run_command(cmd, timeout=5)
    if rc == 0:
        return True
    err_text = (out or "") + ("\n" + err if err else "")
    lowered = err_text.lower()
    # Heuristics for macOS privacy errors
    if any(tok in lowered for tok in ["permission denied", "not permitted", "privacy", "denied"]):
        return False
    # If ffmpeg exists but cannot open device, still likely a permission or device issue.
    if "could not create audio unit" in lowered or "input/output error" in lowered:
        return False
    # Fallback: unknown error, conservatively return False
    return False


def _contains_ci(text: str, needle: str) -> bool:
    return needle.lower() in (text or "").lower()


def _detect_default_output_is_multi_output(text: str) -> bool:
    """Best-effort parse of system_profiler text to see if Multi-Output is the default output device.

    We scan device sections; when inside a device whose name mention Multi-Output, if we
    encounter a line like 'Default Output Device: Yes', we return True.
    """
    if not text:
        return False
    current_name = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Device names appear without colon and often not indented like keys
        if line and not (":" in line and line.split(":", 1)[0].strip().lower() in {
            "default output device", "default input device", "input source", "output source", "manufacturer",
        }):
            current_name = line
        if line.lower().startswith("default output device:"):
            value = line.split(":", 1)[1].strip().lower()
            if value in {"yes", "true"} and current_name and _contains_ci(current_name, "multi-output"):
                return True
    return False


def run_preflight_checks() -> Dict:
    """Run preflight checks for local recording setup on macOS.

    Returns a dict matching RecordingPreflightResponse schema.
    """
    try:
        sp_text = _system_profiler_text()
        sp_json = _system_profiler_json()
        ff_list = _ffmpeg_list_devices()

        # BlackHole detection
        has_blackhole = any([
            _contains_ci(sp_text, "blackhole"),
            _contains_ci(json.dumps(sp_json), "blackhole"),
            _contains_ci(ff_list, "blackhole"),
        ])

        # Multi-Output detection
        has_multi_output = any([
            _contains_ci(sp_text, "multi-output"),
            _contains_ci(json.dumps(sp_json), "multi-output"),
        ])

        # Default output is Multi-Output
        default_output_is_multi = _detect_default_output_is_multi_output(sp_text)

        # Microphone access
        mic_access = _ffmpeg_try_capture()

        recommendations = []
        if not has_blackhole:
            recommendations.append("Install BlackHole 2ch via brew")
        if not has_multi_output:
            recommendations.append("Create a Multi-Output Device in Audio MIDI Setup")
        if has_multi_output and not default_output_is_multi:
            recommendations.append("Set default output to Multi-Output Device in Audio MIDI Setup")
        if not mic_access:
            recommendations.append("Grant microphone access in System Settings > Privacy & Security")

        result = {
            "has_blackhole": bool(has_blackhole),
            "has_multi_output_device": bool(has_multi_output),
            "default_output_is_multi_output": bool(default_output_is_multi),
            "microphone_access_granted": bool(mic_access),
            "recommendations": recommendations,
        }
        logger.info(
            "Preflight results - blackhole=%s multi_output=%s default_is_multi=%s mic_access=%s",
            result["has_blackhole"],
            result["has_multi_output_device"],
            result["default_output_is_multi_output"],
            result["microphone_access_granted"],
        )
        return result
    except Exception as e:
        logger.error(f"Preflight checks failed: {e}", exc_info=True)
        raise

