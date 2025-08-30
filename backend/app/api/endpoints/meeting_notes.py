from fastapi import APIRouter, HTTPException, status, Query, Header
from fastapi.responses import JSONResponse
from typing import Optional

from app.services.meeting_notes_service import meeting_notes_service
from app.services.transcription_service import transcription_service
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.post("/generate-notes/{task_id}")
async def generate_meeting_notes(
    task_id: str,
    template: Optional[str] = Query(None, description="Custom template for note generation"),
    ollama_model: Optional[str] = Query(None, description="Override Ollama model (e.g., llama2:13b, mistral)"),
    ollama_base_url: Optional[str] = Query(None, description="Override Ollama base URL")
):
    """
    Generate meeting notes from a completed transcription task.
    
    Args:
        task_id: The ID of a completed transcription task
        template: Optional custom template for note generation
        
    Returns:
        Generated meeting notes with metadata
    """
    # Check if transcription task exists and is completed
    logger.info(f"Generating meeting notes for transcription task: {task_id}")
    task = transcription_service.tasks.get(task_id)
    if not task:
        logger.error(f"Transcription task not found: {task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription task not found"
        )
    
    if task['status'] != 'completed':
        logger.warning(f"Transcription task {task_id} not completed. Status: {task['status']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transcription task is not completed. Current status: {task['status']}"
        )
    
    if 'result' not in task or 'segments' not in task['result']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcription task does not contain valid segments"
        )
    
    # Check if Ollama is available
    logger.debug("Checking Ollama service availability")
    if not await meeting_notes_service.check_ollama_availability():
        logger.error("Ollama service is not available")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama service is not available. Please ensure Ollama is running."
        )
    
    try:
        # Prepare configuration overrides
        config_overrides = {}
        if ollama_model:
            config_overrides['ollama_model'] = ollama_model
        if ollama_base_url:
            config_overrides['ollama_base_url'] = ollama_base_url
        
        # Generate meeting notes and save to file
        logger.info(f"Generating notes with {len(task['result']['segments'])} segments")
        logger.debug(f"Config overrides: {config_overrides}")
        notes_result = await meeting_notes_service.generate_notes_from_transcript(
            task['result']['segments'],
            template,
            config_overrides,
            save_to_file=True
        )
        logger.info(f"Meeting notes generated successfully for task {task_id}")
        
        return {
            "task_id": task_id,
            "transcription_created_at": task['created_at'],
            "notes_result": notes_result
        }
        
    except Exception as e:
        logger.error(f"Error generating meeting notes for task {task_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating meeting notes: {str(e)}"
        )

@router.get("/ollama/status")
async def check_ollama_status():
    """Check if Ollama service is available and what models are loaded."""
    try:
        logger.debug("Checking Ollama status")
        is_available = await meeting_notes_service.check_ollama_availability()
        
        if not is_available:
            return {
                "status": "unavailable",
                "message": "Ollama service is not running or not accessible"
            }
        
        # Try to get available models
        import requests
        try:
            response = requests.get(f"{meeting_notes_service.base_url}/api/tags", timeout=5)
            models = response.json().get("models", []) if response.status_code == 200 else []
            
            return {
                "status": "available",
                "base_url": meeting_notes_service.base_url,
                "configured_model": meeting_notes_service.model_name,
                "available_models": [model.get("name", "unknown") for model in models]
            }
        except:
            return {
                "status": "available",
                "base_url": meeting_notes_service.base_url,
                "configured_model": meeting_notes_service.model_name,
                "available_models": "unable to fetch"
            }
            
    except Exception as e:
        logger.error(f"Error checking Ollama status: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }
