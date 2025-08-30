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
            if not hf_token:
                logger.warning("HUGGINGFACE_TOKEN not set in environment or settings. Speaker diarization will be disabled.")
                settings.USE_SPEAKER_DIARIZATION = False
                return
                
            try:
                import torchaudio  # noqa: F401  # Just check if it's available
                logger.info(f"Initializing speaker diarization with model: {settings.PYANNOTE_SEGMENTATION_MODEL}")
                
                # Try to load the pipeline
                logger.info("Loading speaker diarization pipeline...")
                self.diarization_pipeline = Pipeline.from_pretrained(
                    settings.PYANNOTE_SEGMENTATION_MODEL,
                    use_auth_token=hf_token
                )
                
                # Test the pipeline with a small audio file to verify it works
                test_audio = os.path.join(os.path.dirname(__file__), "..", "..", "test_audio", "test_440hz.wav")
                if os.path.exists(test_audio):
                    try:
                        logger.info("Testing speaker diarization pipeline...")
                        _ = self.diarization_pipeline(test_audio)
                        logger.info("✓ Speaker diarization pipeline initialized and tested successfully")
                    except Exception as test_e:
                        logger.warning(f"Pipeline initialization test failed: {str(test_e)}")
                        raise
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
                logger.error("1. Invalid or expired Hugging Face token")
                logger.error(f"2. Not accepting the model's terms at https://huggingface.co/{settings.PYANNOTE_SEGMENTATION_MODEL}")
                logger.error("3. Network connectivity issues")
                logger.error("4. Insufficient permissions or quota")
                settings.USE_SPEAKER_DIARIZATION = False
    
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
            
            if use_diarization and (self.diarization_pipeline or hf_token):
                # Initialize diarization pipeline with override token if needed
                pipeline = self.diarization_pipeline
                if hf_token and hf_token != settings.HUGGINGFACE_TOKEN:
                    try:
                        pipeline = Pipeline.from_pretrained(
                            settings.PYANNOTE_SEGMENTATION_MODEL,
                            use_auth_token=hf_token
                        )
                    except Exception as e:
                        print(f"Warning: Failed to initialize diarization with override token: {e}")
                        pipeline = self.diarization_pipeline
                
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
                    speaker = getattr(segment, 'speaker', 'Unknown')
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
            lambda: pipeline_to_use(audio_path, min_speakers=1, max_speakers=10)
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
            new_segments.append(type('Segment', (object,), {
                'start': current_start,
                'end': segment.end,
                'text': current_text.strip(),
                'speaker': current_speaker
            }))

        return new_segments

transcription_service = TranscriptionService()