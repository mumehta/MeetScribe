import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, HTTPException, status, BackgroundTasks, Query, Header
from fastapi.responses import JSONResponse

from app.services.transcription_service import transcription_service
from app.core.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Ensure upload directory exists
os.makedirs(settings.upload_folder_path, exist_ok=True)

@router.post("/transcribe/{processing_task_id}")
async def transcribe_audio(
    processing_task_id: str,
    background_tasks: BackgroundTasks,
    whisper_model: Optional[str] = Query(None, description="Override Whisper model (e.g., small.en, medium.en)"),
    compute_type: Optional[str] = Query(None, description="Override compute type (e.g., int8, float16)"),
    use_diarization: Optional[bool] = Query(None, description="Override speaker diarization setting"),
    hf_token: Optional[str] = Header(None, alias="X-HuggingFace-Token", description="Override HuggingFace token")):
    """
    Transcribe a pre-processed audio file using its processing task ID.
    
    Step 2 of the transcription workflow:
    1. Takes a processing_task_id from the audio upload/conversion step
    2. Performs transcription with speaker diarization
    3. Returns transcription task ID for status tracking
    
    The audio file must already be converted to standard format via /upload-audio endpoint.
    """
    # Import here to avoid circular imports
    from app.services.audio_processing_service import audio_processing_service
    
    # Check if processing task exists and is completed
    logger.info(f"Starting transcription for processing task: {processing_task_id}")
    processing_status = audio_processing_service.get_task_status(processing_task_id)
    if not processing_status:
        logger.error(f"Audio processing task not found: {processing_task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio processing task not found"
        )
    
    if processing_status['status'] != 'completed':
        logger.warning(f"Audio processing not completed for task {processing_task_id}. Status: {processing_status['status']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio processing not completed. Current status: {processing_status['status']}"
        )
    
    if not processing_status.get('converted_file'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No converted audio file available"
        )
    
    # Use the converted audio file
    try:
        converted_file_path = processing_status['converted_file']
        
        # Verify the converted file exists
        if not os.path.exists(converted_file_path):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Converted audio file not found on disk"
            )
        
        # Prepare configuration overrides
        config_overrides = {}
        if whisper_model:
            config_overrides['whisper_model'] = whisper_model
        if compute_type:
            config_overrides['compute_type'] = compute_type
        if use_diarization is not None:
            config_overrides['use_diarization'] = use_diarization
        if hf_token:
            config_overrides['hf_token'] = hf_token
        
        # Create and start transcription task
        logger.info(f"Creating transcription task for file: {converted_file_path}")
        logger.debug(f"Config overrides: {config_overrides}")
        task_id = await transcription_service.create_task(converted_file_path, config_overrides)
        
        # Process in background
        logger.info(f"Starting background transcription task: {task_id}")
        background_tasks.add_task(transcription_service.process_task, task_id)
        
        return {
            "transcription_task_id": task_id, 
            "status": "processing", 
            "processing_task_id": processing_task_id,
            "config_overrides": config_overrides,
            "audio_file_info": processing_status['file_info']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting transcription for task {processing_task_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting transcription: {str(e)}"
        )

@router.get("/transcribe/{task_id}")
async def get_transcription(task_id: str):
    """
    Get the status and result of a transcription task.
    Returns the transcription if complete, or the current status if still processing.
    """
    logger.debug(f"Getting transcription status for task: {task_id}")
    task = transcription_service.tasks.get(task_id)
    if not task:
        logger.warning(f"Transcription task not found: {task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    response = {
        "task_id": task_id,
        "status": task['status'],
        "created_at": task['created_at']
    }
    
    if task['status'] == 'completed':
        response["completed_at"] = task.get('completed_at')
        response["result"] = task['result']
    elif task['status'] == 'error':
        response["error"] = task['error']
        response["completed_at"] = task.get('completed_at')
    
    return response