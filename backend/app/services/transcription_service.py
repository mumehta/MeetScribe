import sys
import warnings
import os
import tempfile
import subprocess
from typing import Union
from pathlib import Path
from typing import Dict, Any, Union
from datetime import datetime
import uuid
import asyncio
import logging

from app.utils.logging_config import get_logger

logger = get_logger(__name__)

import torch
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Any

import torchcodec
from faster_whisper import WhisperModel
from huggingface_hub import HfApi, model_info

from app.core.config import settings
from app.utils.timestamp_utils import generate_transcription_filename, generate_human_readable_timestamp

# Suppress torchaudio warnings
warnings.filterwarnings("ignore", category=UserWarning, module="torchaudio")
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote")

# Import pyannote.audio at module level
try:
    from pyannote.audio import Pipeline
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    if settings.USE_SPEAKER_DIARIZATION:
        print("Warning: pyannote.audio not available. Speaker diarization will be disabled.")
        settings.USE_SPEAKER_DIARIZATION = False

class TranscriptionService:
    def __init__(self):
        self.model = None
        self.diarization_pipeline = None
        self.tasks: Dict[str, Dict] = {}
        
    async def initialize_models(self):
        """Initialize the Whisper model and diarization pipeline"""
        if self.model is None:
            self.model = WhisperModel(
                settings.WHISPER_MODEL,
                compute_type=settings.COMPUTE_TYPE
            )
            
        if settings.USE_SPEAKER_DIARIZATION and self.diarization_pipeline is None and PYAUDIO_AVAILABLE:
            hf_token = os.environ.get('HUGGINGFACE_TOKEN') or settings.HUGGINGFACE_TOKEN
                
            try:
                import torchaudio  # noqa: F401  # Just check if it's available
                logger.info(f"Initializing speaker diarization with model: {settings.PYANNOTE_SEGMENTATION_MODEL}")
                
                # Determine mode early to avoid offline path resolution in online mode
                mode = (settings.DIARIZATION_MODE or 'auto').lower()
                if mode not in {'offline', 'online', 'auto'}:
                    mode = 'auto'

                # If online mode requested, initialize directly from HF Hub and skip local path checks
                if mode == 'online':
                    logger.info("Diarization mode=online: initializing from Hugging Face Hub...")
                    tok = hf_token or settings.HUGGINGFACE_TOKEN
                    if not tok:
                        raise RuntimeError("Online diarization requires HUGGINGFACE_TOKEN.")
                    from pyannote.audio import Pipeline as _Pipeline
                    self.diarization_pipeline = _Pipeline.from_pretrained(
                        settings.PYANNOTE_SEGMENTATION_MODEL or 'pyannote/speaker-diarization-3.1',
                        use_auth_token=tok
                    )
                else:
                    # Load the pipeline (offline-first or auto)
                    logger.info("Loading speaker diarization pipeline (offline-first)...")
                    
                    # Resolve the local model path robustly (handles absence of 'latest' symlink)
                    requested_path = Path(settings.PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH).expanduser()
                
                    # Derive repository root that contains 'refs' and 'snapshots'
                    repo_root = requested_path
                    # If user pointed to a 'snapshots/<something>' or deeper, walk up to repo root
                    parent_names = {p.name for p in repo_root.parents}
                    if repo_root.name == "snapshots" or "snapshots" in parent_names:
                        while repo_root.name != "snapshots" and repo_root.parent != repo_root:
                            repo_root = repo_root.parent
                        if repo_root.name == "snapshots":
                            repo_root = repo_root.parent
                    # If user pointed higher (e.g., sd3.1), jump into pyannote-models/.../models--<org--name>
                    if (repo_root / "pyannote-models").exists():
                        repo_root = repo_root / "pyannote-models" / f"models--{settings.PYANNOTE_SEGMENTATION_MODEL.replace('/', '--')}"
                    
                    # Resolve snapshot via refs/main
                    resolved_model_path = None
                    refs_main = repo_root / "refs" / "main"
                    snapshots_dir = repo_root / "snapshots"
                    try:
                        if refs_main.exists():
                            with open(refs_main, "r", encoding="utf-8") as fh:
                                sha = fh.read().strip()
                            candidate = snapshots_dir / sha
                            if (candidate / "config.yaml").exists():
                                resolved_model_path = candidate
                        # Fallbacks
                        if resolved_model_path is None:
                            # If requested path itself has config.yaml, use it
                            if (requested_path / "config.yaml").exists():
                                resolved_model_path = requested_path
                            # Otherwise pick newest snapshot with config.yaml
                            elif snapshots_dir.exists():
                                candidates = [p for p in snapshots_dir.glob("*") if (p / "config.yaml").exists()]
                                if candidates:
                                    resolved_model_path = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
                    except Exception as e:
                        logger.error(f"Error resolving local pyannote model path: {e}")
                        resolved_model_path = None
                    
                    # Validate final path
                    if resolved_model_path is None or not (resolved_model_path / "config.yaml").exists():
                        logger.error("Unable to locate a valid local pyannote model directory. Looked under: %s", repo_root)
                        settings.USE_SPEAKER_DIARIZATION = False
                        return
                    
                    model_path = resolved_model_path
                    logger.info(f"Using model from: {model_path}")
                
                # If online mode requested, try online first; else offline-first
                def _set_offline_env(on: bool):
                    if on:
                        os.environ['HF_HUB_OFFLINE'] = '1'
                        os.environ['TRANSFORMERS_OFFLINE'] = '1'
                    else:
                        os.environ.pop('HF_HUB_OFFLINE', None)
                        os.environ.pop('TRANSFORMERS_OFFLINE', None)

                # Only reset if we haven't already set a pipeline (e.g., online fast path above)
                if self.diarization_pipeline is None:
                    self.diarization_pipeline = None
                # Always set cache path for pyannote when using local model path
                if mode != 'online':
                    os.environ['PYANNOTE_CACHE'] = str(model_path.parent)

                def _load_offline():
                    _set_offline_env(True)
                    kwargs = {}
                    if hf_token:
                        kwargs['use_auth_token'] = hf_token
                    config_path = Path(model_path) / "config.yaml"
                    return Pipeline.from_pretrained(str(config_path), **kwargs)

                def _load_online():
                    _set_offline_env(False)
                    tok = hf_token or settings.HUGGINGFACE_TOKEN
                    if not tok:
                        raise RuntimeError("Online diarization requires HUGGINGFACE_TOKEN.")
                    return Pipeline.from_pretrained(
                        settings.PYANNOTE_SEGMENTATION_MODEL or 'pyannote/speaker-diarization-3.1',
                        use_auth_token=tok
                    )

                try:
                    if mode == 'online' and self.diarization_pipeline is None:
                        logger.info("Diarization mode=online: trying online model load...")
                        self.diarization_pipeline = _load_online()
                    elif mode == 'offline':
                        logger.info("Diarization mode=offline: trying offline local model load...")
                        self.diarization_pipeline = _load_offline()
                    else:
                        # auto: offline first then online
                        logger.info("Diarization mode=auto: trying offline load, with online fallback if token available...")
                        try:
                            self.diarization_pipeline = _load_offline()
                        except Exception as off_e:
                            logger.warning(f"Offline diarization load failed: {off_e}")
                            if hf_token or settings.HUGGINGFACE_TOKEN:
                                try:
                                    self.diarization_pipeline = _load_online()
                                except Exception as on_e:
                                    logger.error(f"Online diarization load failed: {on_e}")
                                    self.diarization_pipeline = None
                            else:
                                logger.info("No token available; skipping online fallback.")
                
                    
                    # Test the pipeline with a small audio file to verify it works
                    test_audio = os.path.join(os.path.dirname(__file__), "..", "..", "test_audio", "test_440hz.wav")
                    if os.path.exists(test_audio):
                        try:
                            logger.info("Testing speaker diarization pipeline...")
                            _ = self.diarization_pipeline(test_audio)
                            logger.info("✓ Speaker diarization pipeline initialized and tested successfully")
                        except Exception as test_e:
                            logger.warning(f"Speaker diarization test failed: {str(test_e)}")
                            logger.warning("Continuing without speaker diarization")
                            settings.USE_SPEAKER_DIARIZATION = False
                except Exception as e:
                    logger.error(f"Failed to initialize speaker diarization: {str(e)}")
                    logger.error("Please ensure all model files are downloaded and accessible locally")
                    settings.USE_SPEAKER_DIARIZATION = False
                else:
                    logger.info("Speaker diarization pipeline initialized (test audio not found for verification)")
                
            except ImportError as e:
                logger.warning(f"{str(e)}. Speaker diarization will be disabled.")
                if 'No module named' in str(e):
                    logger.warning("Please install required packages: pip install torchaudio pyannote.audio")
                settings.USE_SPEAKER_DIARIZATION = False
            except Exception as e:
                logger.error(f"Failed to initialize speaker diarization: {str(e)}")
                logger.error("This could be due to:")
                logger.error("1. Invalid local pyannote model path or missing files (config.yaml)")
                logger.error("2. Corrupted or incomplete local cache extraction")
                logger.error("3. Incompatible pyannote/audio or torchaudio installation")
                logger.error("If you intend to run online, ensure token access and model terms are accepted.")
                settings.USE_SPEAKER_DIARIZATION = False
    
    def _load_diarization_pipeline(self, hf_token: Optional[str] = None, mode: Optional[str] = None):
        """Load pyannote pipeline according to mode ('offline'|'online'|'auto'). Returns pipeline or None."""
        if not PYAUDIO_AVAILABLE:
            return None
        try:
            import torchaudio  # noqa: F401
        except Exception:
            return None

        try:
            mode = (mode or settings.DIARIZATION_MODE or 'auto').lower()
            if mode not in {'offline', 'online', 'auto'}:
                mode = 'auto'

            # Helper to toggle offline env flags
            def _set_offline_env(on: bool):
                if on:
                    os.environ['HF_HUB_OFFLINE'] = '1'
                    os.environ['TRANSFORMERS_OFFLINE'] = '1'
                else:
                    os.environ.pop('HF_HUB_OFFLINE', None)
                    os.environ.pop('TRANSFORMERS_OFFLINE', None)

            # If explicitly online, skip any local path resolution and load from HF
            if mode == 'online':
                _set_offline_env(False)
                tok = hf_token or settings.HUGGINGFACE_TOKEN
                if not tok:
                    logger.error("Online diarization requires HUGGINGFACE_TOKEN but none was provided.")
                    return None
                return Pipeline.from_pretrained(
                    settings.PYANNOTE_SEGMENTATION_MODEL or 'pyannote/speaker-diarization-3.1',
                    use_auth_token=tok,
                    local_files_only=False
                )

            requested_path = Path(settings.PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH).expanduser()
            repo_root = requested_path
            parent_names = {p.name for p in repo_root.parents}
            if repo_root.name == "snapshots" or "snapshots" in parent_names:
                while repo_root.name != "snapshots" and repo_root.parent != repo_root:
                    repo_root = repo_root.parent
                if repo_root.name == "snapshots":
                    repo_root = repo_root.parent
            if (repo_root / "pyannote-models").exists():
                repo_root = repo_root / "pyannote-models" / f"models--{settings.PYANNOTE_SEGMENTATION_MODEL.replace('/', '--')}"

            resolved_model_path = None
            refs_main = repo_root / "refs" / "main"
            snapshots_dir = repo_root / "snapshots"
            if refs_main.exists():
                with open(refs_main, "r", encoding="utf-8") as fh:
                    sha = fh.read().strip()
                candidate = snapshots_dir / sha
                if (candidate / "config.yaml").exists():
                    resolved_model_path = candidate
            if resolved_model_path is None:
                if (requested_path / "config.yaml").exists():
                    resolved_model_path = requested_path
                elif snapshots_dir.exists():
                    candidates = [p for p in snapshots_dir.glob("*") if (p / "config.yaml").exists()]
                    if candidates:
                        resolved_model_path = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]

            if resolved_model_path is None or not (resolved_model_path / "config.yaml").exists():
                logger.error("Unable to locate a valid local pyannote model directory for offline load.")
                return None

            # Always set cache path when using local model path
            model_path = resolved_model_path
            os.environ['PYANNOTE_CACHE'] = str(model_path.parent)

            def _load_offline():
                _set_offline_env(True)
                kwargs = {}
                if hf_token:
                    kwargs['use_auth_token'] = hf_token
                config_path = Path(model_path) / "config.yaml"
                return Pipeline.from_pretrained(str(config_path), **kwargs)

            def _load_online():
                _set_offline_env(False)
                tok = hf_token or settings.HUGGINGFACE_TOKEN
                if not tok:
                    raise RuntimeError("Online diarization requires HUGGINGFACE_TOKEN.")
                return Pipeline.from_pretrained(
                    settings.PYANNOTE_SEGMENTATION_MODEL or 'pyannote/speaker-diarization-3.1',
                    use_auth_token=tok
                )

            if mode == 'online':
                return _load_online()
            if mode == 'offline':
                return _load_offline()
            # auto
            try:
                return _load_offline()
            except Exception as off_e:
                logger.warning(f"Offline diarization load failed: {off_e}")
                if hf_token or settings.HUGGINGFACE_TOKEN:
                    try:
                        return _load_online()
                    except Exception as on_e:
                        logger.error(f"Online diarization load failed: {on_e}")
                        return None
                return None
        except Exception as e:
            logger.error(f"Offline diarization pipeline load failed: {e}")
            return None

    async def create_task(self, audio_path: str, config_overrides: Dict[str, Any] = None) -> str:
        """Create a new transcription task with optional configuration overrides"""
        import uuid
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            'status': 'processing',
            'audio_path': audio_path,
            'config_overrides': config_overrides or {},
            'result': None,
            'error': None,
            'created_at': datetime.utcnow().isoformat()
        }
        return task_id
    
    async def process_task(self, task_id: str):
        """Process a transcription task"""
        logger.info(f"Starting processing task {task_id}")
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
            
        try:
            logger.info(f"Processing audio file: {task['audio_path']}")
            if not os.path.exists(task['audio_path']):
                error_msg = f"Audio file not found: {task['audio_path']}"
                logger.error(error_msg)
                task.update({
                    'status': 'error',
                    'error': error_msg,
                    'completed_at': datetime.utcnow().isoformat()
                })
                return
                
            # Process the audio with config overrides and save to file
            logger.info(f"Calling process_audio with save_to_file=True")
            result = await self.process_audio(task['audio_path'], task.get('config_overrides', {}), save_to_file=True)
            
            # Update task with result
            logger.info(f"Task {task_id} completed successfully")
            task.update({
                'status': 'completed',
                'result': result,
                'completed_at': datetime.utcnow().isoformat()
            })
            
            # Skip cleanup to preserve the audio file
            logger.info(f"Preserving audio file: {task['audio_path']}")
            # Only clean up if it's a temporary file in the system temp directory
            if task['audio_path'].startswith(tempfile.gettempdir()):
                try:
                    os.unlink(task['audio_path'])
                    temp_dir = os.path.dirname(task['audio_path'])
                    if os.path.basename(temp_dir).startswith('tmp'):
                        os.rmdir(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {task['audio_path']}: {str(e)}")
                
        except Exception as e:
            task.update({
                'status': 'error',
                'error': str(e),
                'completed_at': datetime.utcnow().isoformat()
            })
    
    async def process_audio(self, audio_path: str, config_overrides: Dict[str, Any] = None, save_to_file=False) -> Dict:
        """Process audio file and return transcription with optional config overrides"""
        config_overrides = config_overrides or {}
        
        # Convert audio to WAV if needed
        wav_path = await self._convert_to_wav(audio_path)
        
        try:
            # Transcribe audio with config overrides
            segments_generator, info = await self._transcribe_audio(wav_path, config_overrides)
            segments = list(segments_generator)
            
            # Apply speaker diarization if enabled (check both settings and overrides)
            use_diarization = config_overrides.get('use_diarization', settings.USE_SPEAKER_DIARIZATION)
            hf_token = config_overrides.get('hf_token', settings.HUGGINGFACE_TOKEN)
            # Allow overriding mode at request-time (also accept legacy 'offline' bool)
            diarization_mode = config_overrides.get('diarization_mode')
            if diarization_mode is None and 'offline' in config_overrides:
                diarization_mode = 'offline' if config_overrides.get('offline') else 'online'

            if use_diarization:
                # Ensure we have a pipeline; prefer existing, otherwise load offline-first (optionally with token)
                pipeline = self.diarization_pipeline or self._load_diarization_pipeline(hf_token, diarization_mode)
                if pipeline is None and hf_token:
                    # Last attempt: try loading with token explicitly (still local-only)
                    try:
                        pipeline = self._load_diarization_pipeline(hf_token, diarization_mode)
                    except Exception:
                        pipeline = None
                if pipeline:
                    diarization = await self._diarize_audio(wav_path, pipeline)
                    segments = self._combine_speaker_segments(segments, diarization)
            
            full_transcript = '\n'.join([s.text for s in segments])
            return {
                'text': full_transcript,
                'segments': [{
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text,
                    'speaker': getattr(segment, 'speaker', 'SPEAKER_00')
                } for segment in segments],
                'language': info.language,
                'language_probability': info.language_probability
            }
            
        finally:
            # Clean up the WAV file if it was created
            if wav_path != audio_path and os.path.exists(wav_path):
                os.unlink(wav_path)
            
            # Save transcription to final output folder with timestamp
            if save_to_file:
                timestamp = generate_human_readable_timestamp()
                filename = generate_transcription_filename(timestamp)
                output_path = settings.final_output_folder_path / filename
                
                # Ensure final output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Format transcript as markdown
                markdown_content = f"# Transcription\n\n**Generated:** {datetime.utcnow().isoformat()}\n\n## Full Transcript\n\n{full_transcript}\n\n## Segments\n\n"
                for segment in segments:
                    start_time = f"{int(segment.start // 60):02d}:{int(segment.start % 60):02d}"
                    speaker = getattr(segment, 'speaker', 'SPEAKER_00')
                    markdown_content += f"**[{start_time}] {speaker}:** {segment.text.strip()}\n\n"
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                logger.info(f"Transcription saved to: {output_path}")
                
                # Note: final_output_file path stored for reference
                # (task context not available in this scope)
    
    async def _convert_to_wav(self, audio_path: Union[str, Path]) -> str:
        """Converts an audio file to WAV format if it's not already."""
        audio_path_str = str(audio_path)
        if audio_path_str.lower().endswith('.wav'):
            return audio_path_str
            
        temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        
        try:
            cmd = [
                'ffmpeg', '-y', '-i', audio_path_str,
                '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                '-loglevel', 'error', temp_wav
            ]
            
            subprocess.run(cmd, check=True)
            return temp_wav
            
        except subprocess.CalledProcessError as e:
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)
            raise Exception(f"Audio conversion failed: {str(e)}")
    
    async def _transcribe_audio(self, audio_path: str, config_overrides: Dict[str, Any] = None):
        """Transcribe audio using Whisper with optional config overrides"""
        config_overrides = config_overrides or {}
        
        # Get model settings (use overrides or defaults)
        whisper_model = config_overrides.get('whisper_model', settings.WHISPER_MODEL)
        compute_type = config_overrides.get('compute_type', settings.COMPUTE_TYPE)
        
        # Initialize model with overrides if different from current
        model_to_use = self.model
        if (whisper_model != settings.WHISPER_MODEL or 
            compute_type != settings.COMPUTE_TYPE):
            try:
                model_to_use = WhisperModel(whisper_model, compute_type=compute_type)
            except Exception as e:
                print(f"Warning: Failed to load override model {whisper_model}, using default: {e}")
                model_to_use = self.model
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: model_to_use.transcribe(
                    audio_path,
                    language="en",
                    word_timestamps=True,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
            )
    
    async def _diarize_audio(self, audio_path: str, pipeline=None):
        """Apply speaker diarization to audio"""
        pipeline_to_use = pipeline or self.diarization_pipeline
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: pipeline_to_use(
                audio_path,
                min_speakers=getattr(settings, 'DIARIZATION_MIN_SPEAKERS', 1),
                max_speakers=getattr(settings, 'DIARIZATION_MAX_SPEAKERS', 10)
            )
        )
    
    def _combine_speaker_segments(self, segments, diarization):
        """Combine Whisper segments with speaker diarization using word-level timestamps."""
        logger.info("--- Diarization Debug ---")
        logger.info(f"Num transcription segments: {len(segments)}")
        if segments:
            for i, seg in enumerate(segments):
                logger.info(f"  Segment {i}: {seg.start:.2f}s - {seg.end:.2f}s, Text: '{seg.text}'")
        
        logger.info("Diarization output:")
        speaker_count = 0
        if diarization:
            speakers_found = set()
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speakers_found.add(speaker)
                logger.info(f"  {speaker}: {turn.start:.2f}s - {turn.end:.2f}s")
            speaker_count = len(speakers_found)
            logger.info(f"Total unique speakers detected: {speaker_count}")
        else:
            logger.warning("No diarization data available - all segments will be assigned to SPEAKER_00")
        logger.info("-------------------------")

        if not diarization:
            for seg in segments:
                seg.speaker = 'SPEAKER_00'
            return segments

        # Create a timeline of speakers from diarization
        speaker_timeline = {}
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            for i in range(int(turn.start * 100), int(turn.end * 100)):
                speaker_timeline[i] = speaker

        if not speaker_timeline:
            # No speaker intervals mapped (edge-case): fallback to SPEAKER_00 for all
            logger.warning("Empty speaker timeline from diarization - assigning SPEAKER_00 to all segments")
            for seg in segments:
                seg.speaker = 'SPEAKER_00'
            return segments

        new_segments = []
        for segment in segments:
            if not hasattr(segment, 'words') or not segment.words:
                # If no word timestamps, use the old logic for the segment
                speakers = [speaker_timeline.get(i) for i in range(int(segment.start * 100), int(segment.end * 100))]
                valid_speakers = [s for s in speakers if s is not None]
                segment.speaker = max(set(valid_speakers), key=valid_speakers.count) if valid_speakers else 'SPEAKER_00'
                new_segments.append(segment)
                continue

            current_speaker = None
            current_text = ""
            current_start = segment.words[0].start

            for word in segment.words:
                # Check a small range around the word's midpoint for a speaker
                start_check = int(word.start * 100)
                end_check = int(word.end * 100)
                speaker = 'SPEAKER_00'
                for i in range(start_check, end_check + 1):
                    if i in speaker_timeline:
                        speaker = speaker_timeline[i]
                        break
                if speaker == 'SPEAKER_00': # Fallback to midpoint if range check fails
                    word_mid_point = int(((word.start + word.end) / 2) * 100)
                    speaker = speaker_timeline.get(word_mid_point, 'SPEAKER_00')

                # Minimal per-word debug to catch mapping issues (rate-limited by segments)
                logger.debug(f"word '{getattr(word, 'word', '')}' [{word.start:.2f},{word.end:.2f}] -> {speaker}")

                if current_speaker is None:
                    current_speaker = speaker

                if speaker != current_speaker:
                    # End of a segment
                    new_segments.append(type('Segment', (object,), {
                        'start': current_start,
                        'end': word.start,
                        'text': current_text.strip(),
                        'speaker': current_speaker
                    }))
                    # Start of a new segment
                    current_speaker = speaker
                    current_text = ""
                    current_start = word.start
                
                current_text += word.word + " "

            # Add the last segment
            if current_speaker is None:
                # Safety: ensure we never emit a segment without a speaker label
                current_speaker = 'SPEAKER_00'
            new_segments.append(type('Segment', (object,), {
                'start': current_start,
                'end': segment.end,
                'text': current_text.strip(),
                'speaker': current_speaker
            }))

        return new_segments

transcription_service = TranscriptionService()