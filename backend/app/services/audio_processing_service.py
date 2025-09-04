import os
import tempfile
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, Union
from datetime import datetime
import uuid
import shutil
import logging

from app.core.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

class AudioProcessingService:
    def __init__(self):
        self.processing_tasks: Dict[str, Dict] = {}
        
    async def create_processing_task(self, uploaded_file_path: str, original_filename: str) -> str:
        """Create a new audio processing task for file analysis and conversion"""
        task_id = str(uuid.uuid4())
        
        # Analyze file type and properties
        file_info = await self._analyze_audio_file(uploaded_file_path, original_filename)
        
        self.processing_tasks[task_id] = {
            'status': 'analyzing',
            'original_file': uploaded_file_path,
            'original_filename': original_filename,
            'file_info': file_info,
            'converted_file': None,
            'created_at': datetime.utcnow().isoformat(),
            'error': None
        }
        
        return task_id
    
    async def process_audio_file(self, task_id: str) -> bool:
        """Process (convert) the audio file to standard format"""
        task = self.processing_tasks.get(task_id)
        if not task:
            return False
            
        try:
            task['status'] = 'converting'
            
            # Convert to standard WAV format
            converted_path = await self._convert_to_standard_wav(
                task['original_file'], 
                task['original_filename']
            )
            
            task.update({
                'status': 'completed',
                'converted_file': converted_path,
                'completed_at': datetime.utcnow().isoformat()
            })
            
            logger.info(f"Audio processing completed for task {task_id}")
            return True
            
        except Exception as e:
            task.update({
                'status': 'error',
                'error': str(e),
                'completed_at': datetime.utcnow().isoformat()
            })
            logger.error(f"Audio processing failed for task {task_id}: {str(e)}")
            return False
    
    async def _analyze_audio_file(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Analyze audio file properties"""
        file_ext = Path(filename).suffix.lower()[1:] if filename else ''
        file_size = os.path.getsize(file_path)
        
        # Basic file info
        info = {
            'original_format': file_ext,
            'file_size_bytes': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2),
            'supported': file_ext in settings.ALLOWED_EXTENSIONS
        }
        
        # Try to get audio properties using ffprobe if available
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', '-show_streams', file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            import json
            probe_data = json.loads(result.stdout)
            
            if 'format' in probe_data:
                format_info = probe_data['format']
                info.update({
                    'duration_seconds': float(format_info.get('duration', 0)),
                    'bit_rate': int(format_info.get('bit_rate', 0)),
                    'format_name': format_info.get('format_name', '')
                })
            
            # Get audio stream info
            audio_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']
            if audio_streams:
                stream = audio_streams[0]
                info.update({
                    'codec': stream.get('codec_name', ''),
                    'sample_rate': int(stream.get('sample_rate', 0)),
                    'channels': int(stream.get('channels', 0))
                })
                
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            # ffprobe not available or failed, use basic info
            logger.warning(f"Could not analyze audio properties for {filename}")
            info.update({
                'duration_seconds': 0,
                'codec': 'unknown',
                'sample_rate': 0,
                'channels': 0
            })
        
        return info
    
    async def _convert_to_standard_wav(self, audio_path: str, original_filename: str) -> str:
        """Convert audio file to standard WAV format (16kHz, mono, 16-bit PCM).
        Uses asyncio subprocess to avoid blocking the event loop.
        """
        # If already WAV, check if it meets our standards
        if original_filename.lower().endswith('.wav'):
            # Could add validation here to check if it's already in standard format
            pass
        
        # Generate output path in the same directory as the original file
        audio_dir = Path(audio_path).parent
        base_name = Path(original_filename).stem
        output_filename = f"{base_name}_converted.wav"
        output_path = audio_dir / output_filename
        
        # Ensure output directory exists
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Ensure the output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Ensure the output file doesn't exist
            if output_path.exists():
                output_path.unlink()
                
            cmd = (
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-i', str(audio_path),  # Input file
                '-vn',  # Disable video
                '-acodec', 'pcm_s16le',  # 16-bit PCM
                '-ar', '16000',          # 16kHz sample rate
                '-ac', '1',              # Mono
                '-loglevel', 'error',
                str(output_path)  # Output file
            )
            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _out, err = await proc.communicate()
            if proc.returncode != 0:
                error_msg = f"FFmpeg failed with return code {proc.returncode}. "
                error_msg += f"Stderr: {err.decode('utf-8', errors='ignore')}" if err else "No error output"
                logger.error(error_msg)
                raise Exception(f"Audio conversion failed: {error_msg}")
                
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise Exception(f"Output file was not created or is empty: {output_path}")
                
            logger.info(f"Successfully converted {original_filename} to {output_path} (Size: {output_path.stat().st_size} bytes)")
            return str(output_path)
            
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg command failed: {str(e)}\n"
            if hasattr(e, 'stderr') and e.stderr:
                error_msg += f"FFmpeg stderr: {e.stderr}"
            logger.error(error_msg)
            raise Exception(f"Audio conversion failed: {error_msg}")
        except Exception as e:
            logger.error(f"Unexpected error during audio conversion: {str(e)}")
            raise
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of an audio processing task"""
        task = self.processing_tasks.get(task_id)
        if not task:
            return None
        
        response = {
            'task_id': task_id,
            'status': task['status'],
            'created_at': task['created_at'],
            'file_info': task['file_info']
        }
        
        if task['status'] == 'completed':
            response.update({
                'completed_at': task.get('completed_at'),
                'converted_file': task['converted_file']
            })
        elif task['status'] == 'error':
            response.update({
                'error': task['error'],
                'completed_at': task.get('completed_at')
            })
        
        return response

# Global service instance
audio_processing_service = AudioProcessingService()
