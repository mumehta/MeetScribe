import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, HTTPException, status, BackgroundTasks

from app.services.audio_processing_service import audio_processing_service
from app.core.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Ensure upload directory exists
os.makedirs(settings.upload_folder_path, exist_ok=True)

@router.post("/upload-audio")
async def upload_audio_file(file: UploadFile,background_tasks: BackgroundTasks):
    """
    Upload and analyze an audio file, then convert it to standard format.
    
    Step 1 of the transcription workflow:
    1. Upload audio file
    2. Analyze file type and properties  
    3. Convert to standard WAV format (16kHz, mono, 16-bit PCM)
    
    Returns a processing task ID for tracking conversion progress.
    """
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
            file.filename
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


