import os
import shutil
import tempfile
import json
import subprocess
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, HTTPException, status, BackgroundTasks, Request
from pydantic import BaseModel, Field, ValidationError

from app.services.audio_processing_service import audio_processing_service
from app.core.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Ensure upload directory exists
os.makedirs(settings.upload_folder_path, exist_ok=True)

class Provenance(BaseModel):
    source: Optional[str] = Field(default=None, description="Origin of the audio (e.g., 'recording')")
    recording_task_id: Optional[str] = Field(default=None, description="Optional ID of the recording task")


class ServerLocalUploadRequest(BaseModel):
    server_local_path: str = Field(..., description="Absolute path on the server to an existing audio file")
    provenance: Optional[Provenance] = None


def _is_within_workspace(p: Path, base: Path) -> bool:
    try:
        p_resolved = p.resolve(strict=False)
        base_resolved = base.resolve(strict=True)
        return str(p_resolved).startswith(str(base_resolved) + os.sep) or p_resolved == base_resolved
    except Exception:
        return False


def _ffprobe_has_audio_stream(file_path: str) -> bool:
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_type', '-of', 'json', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout or '{}')
        streams = data.get('streams', [])
        return any(s.get('codec_type') == 'audio' for s in streams)
    except Exception:
        return False


@router.post("/upload-audio")
async def upload_audio_file(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Upload and analyze an audio file, then convert it to standard format.
    
    Step 1 of the transcription workflow:
    1. Upload audio file
    2. Analyze file type and properties  
    3. Convert to standard WAV format (16kHz, mono, 16-bit PCM)
    
    Returns a processing task ID for tracking conversion progress.
    """
    # Determine content type and parse accordingly
    content_type = request.headers.get('content-type', '')
    file = None
    json_body: Optional[ServerLocalUploadRequest] = None
    try:
        if 'application/json' in content_type:
            payload = await request.json()
            try:
                json_body = ServerLocalUploadRequest(**payload)
            except ValidationError as ve:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON body: {ve}")
        elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            form = await request.form()
            file = form.get('file')
        else:
            # Try JSON as a last resort
            try:
                payload = await request.json()
                json_body = ServerLocalUploadRequest(**payload)
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported Content-Type. Use multipart/form-data or application/json")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse request body: {e}")

    # Enforce mutual exclusivity between multipart and JSON modes
    has_file = file is not None
    has_json = json_body is not None
    if (has_file and has_json) or (not has_file and not has_json):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either multipart file upload or JSON body with server_local_path, not both"
        )
    
    # Branch: multipart upload (existing behavior)
    if has_file:
        # Validate file type
        logger.info(f"Uploading audio file: {file.filename}")
        file_ext = Path(file.filename).suffix.lower()[1:] if file.filename else ''
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            logger.warning(f"Invalid file type '{file_ext}' for file: {file.filename}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type '{file_ext}'. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )
        # Save uploaded file to temporary location
        try:
            # Create a temporary directory for this upload in intermediate folder
            settings.intermediate_folder_path.mkdir(parents=True, exist_ok=True)
            temp_dir = tempfile.mkdtemp(dir=str(settings.intermediate_folder_path))
            temp_path = os.path.join(temp_dir, file.filename)
            
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Create processing task
            logger.info(f"Creating audio processing task for file: {file.filename}")
            task_id = await audio_processing_service.create_processing_task(
                temp_path, 
                file.filename,
                input_type="multipart",
                provenance=None,
            )
            
            # Start background processing
            logger.info(f"Starting background audio processing task: {task_id}")
            background_tasks.add_task(
                audio_processing_service.process_audio_file, 
                task_id
            )
            
            return {
                "processing_task_id": task_id,
                "status": "analyzing",
                "message": "Audio file uploaded successfully. Analysis and conversion in progress."
            }
            
        except Exception as e:
            logger.error(f"Error processing uploaded file {file.filename}: {str(e)}", exc_info=True)
            # Clean up temporary directory if it was created
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file: {str(e)}"
            )

    # Branch: server-local path registration (new behavior)
    assert json_body is not None
    server_path_str = json_body.server_local_path
    provenance = json_body.provenance.dict() if json_body.provenance else None
    logger.info(f"Registering server-local audio path: {server_path_str}")
    logger.debug(f"JSON mode provenance: {provenance}")
    logger.debug(f"Allow-list root: {settings.workspace_root_path}")

    # Validations
    try:
        server_path = Path(server_path_str)
        logger.debug(f"Resolved server path (non-strict): {server_path.resolve(strict=False)}")
        if not server_path.is_absolute():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="server_local_path must be an absolute path")
        # Reject symlinks outright
        if server_path.is_symlink():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Symlinks are not allowed for server_local_path")
        # Path existence and regular file
        if not server_path.exists():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="server_local_path does not exist")
        if not server_path.is_file():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="server_local_path must be a regular file")
        # Allow-list: must be within workspace root
        if not _is_within_workspace(server_path, settings.workspace_root_path):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="server_local_path is outside the allowed workspace")
        # Non-empty
        if server_path.stat().st_size <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file is empty")
        # File type by extension
        ext = server_path.suffix.lower()[1:] if server_path.suffix else ''
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid file type '{ext}'. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}")
        # Minimal probe to ensure it's an audio container
        if not _ffprobe_has_audio_stream(str(server_path)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provided file is not a valid/parsable audio")

        # Create processing task (do not copy/move the original file)
        original_filename = server_path.name
        task_id = await audio_processing_service.create_processing_task(
            str(server_path),
            original_filename,
            input_type="server_local",
            provenance=provenance,
        )

        # Start background processing (normalization/convert)
        logger.info(f"Starting background audio processing task: {task_id}")
        background_tasks.add_task(audio_processing_service.process_audio_file, task_id)

        return {
            "processing_task_id": task_id,
            "status": "analyzing",
            "message": "Audio path registered. Analysis and conversion in progress."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering server-local path {server_path_str}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error during audio registration")

@router.get("/audio-processing/{task_id}")
async def get_audio_processing_status(task_id: str):
    """
    Get the status of an audio processing task.
    
    Returns file analysis results and conversion status.
    When completed, provides path to converted audio file.
    """
    logger.debug(f"Getting audio processing status for task: {task_id}")
    task_status = audio_processing_service.get_task_status(task_id)
    
    if not task_status:
        logger.warning(f"Audio processing task not found: {task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio processing task not found"
        )
    
    return task_status
