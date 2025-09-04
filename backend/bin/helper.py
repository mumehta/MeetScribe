#!/usr/bin/env python3
"""
Helper functions for the Meeting Transcriber API.
"""
import os
import sys
import time
import requests
import json
from typing import Dict, Any, Optional

# Uploads a meeting file and converts to standard (.wav) format - intermediatory step
# Returns task ID when conversion is completed
def get_content_type(file_path: str) -> str:
    """Get the appropriate content type based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return {
        '.wav': 'audio/wav',
        '.mp3': 'audio/mpeg',
        '.m4a': 'audio/mp4',
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.ogg': 'audio/ogg',
        '.flac': 'audio/flac',
        '.webm': 'audio/webm'
    }.get(ext, 'application/octet-stream')

def upload_and_standardize_audio(file_path: str, api_base_url: str = "http://localhost:8000") -> str:
    """
    Upload and standardize an audio file.
    
    Args:
        file_path (str): Path to the audio file
        api_base_url (str): Base URL of the API
        
    Returns:
        str: Task ID for tracking the processing status
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    url = f"{api_base_url}/api/v1/upload-audio"
    file_name = os.path.basename(file_path)
    content_type = get_content_type(file_path)
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_name, f, content_type)}
            response = requests.post(
                url,
                files=files,
                headers={'Accept': 'application/json'}
            )
        
        response.raise_for_status()
        result = response.json()
        
        # Check for either task_id or processing_task_id in the response
        task_id = result.get('task_id') or result.get('processing_task_id')
        if not task_id:
            raise Exception(f"No task ID found in response: {result}")
            
        return task_id
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to upload file: {str(e)}"
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f"\nStatus: {e.response.status_code}"
            try:
                error_msg += f"\nResponse: {e.response.text}"
            except:
                pass
        raise Exception(error_msg)
    except Exception as e:
        raise Exception(f"Error during upload: {str(e)}")

# Transcribe audio file
# Required parameters:
# processing_task_id: The task ID from upload_and_standardize_audio
# hf_token: HuggingFace token for speaker diarization - Either provide from environment variable or as argument
# Optional parameters:
# api_base_url: Base URL of the API - Default: http://localhost:8000
# whisper_model: Override default Whisper model - Default: None
# compute_type: Override compute type (e.g., int8, float16) - Default: None
# Returns:
# Transcription result containing text, segments, and metadata
def transcribe_audio(processing_task_id: str, 
                   hf_token: Optional[str] = None,
                   api_base_url: str = "http://localhost:8000",
                   whisper_model: Optional[str] = None,
                   compute_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Start transcription of a processed audio file and wait for completion.
    
    Args:
        processing_task_id (str): The task ID from upload_and_standardize_audio
        hf_token (str, optional): HuggingFace token for speaker diarization. 
                                 If not provided, will try to read from HUGGINGFACE_TOKEN environment variable.
        api_base_url (str): Base URL of the API
        whisper_model (str, optional): Override default Whisper model
        compute_type (str, optional): Override compute type (e.g., int8, float16)
        
    Returns:
        dict: Transcription result containing text, segments, and metadata
        
    Raises:
        Exception: If transcription fails or times out (10 minutes)
    """
    # Get HF token from environment if not provided
    hf_token = hf_token or os.environ.get("HUGGINGFACE_TOKEN")
    if not hf_token:
        raise ValueError(
            "HuggingFace token is required. Either pass it as an argument "
            "or set the HUGGINGFACE_TOKEN environment variable."
        )
    
    # Prepare headers and query params
    headers = {"X-HuggingFace-Token": hf_token}
    params = {}
    
    if whisper_model:
        params["whisper_model"] = whisper_model
    if compute_type:
        params["compute_type"] = compute_type
    
    # Start transcription
    response = requests.post(
        f"{api_base_url}/api/v1/transcribe/{processing_task_id}",
        headers=headers,
        params=params,
        timeout=300  # Increased to 300 seconds (5 minutes) to handle large jobs
    )
    
    if response.status_code != 200:
        raise Exception(f"Transcription start failed: {response.status_code} - {response.text}")
    
    result = response.json()
    task_id = result.get('transcription_task_id')
    
    if not task_id:
        raise Exception(f"No transcription_task_id returned from transcription start. Response: {result}")
    
    # Poll for completion
    start_time = time.time()
    while time.time() - start_time < 3600:  # Increased to 60 minutes to handle long transcriptions
        response = requests.get(
            f"{api_base_url}/api/v1/transcribe/{task_id}",
            timeout=300  # Increased to 300 seconds per poll
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get transcription status: {response.status_code} - {response.text}")
            
        status_data = response.json()
        status = status_data.get('status')
        
        if status == 'completed':
            return status_data
        elif status in ('failed', 'error'):
            raise Exception(f"Transcription failed: {status_data.get('error', 'Unknown error')}")
            
        time.sleep(5)
    
    raise Exception("Transcription timed out after 10 minutes")


def generate_meeting_notes(transcription_task_id: str, 
                         template: Optional[str] = None,
                         ollama_model: Optional[str] = None,
                         ollama_base_url: str = "http://localhost:11434",
                         api_base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """
    Generate meeting notes from a completed transcription task.
    
    Args:
        transcription_task_id (str): The task ID from a completed transcription
        template (str, optional): Custom template for note generation. If not provided,
                                the server will use a default template that includes:
                                - Meeting summary
                                - Key points
                                - Action items
                                - Decisions made
        ollama_model (str, optional): Override default Ollama model (e.g., "llama2:13b").
                                     If not provided, uses the server's default model.
        ollama_base_url (str): Base URL of the Ollama API. Defaults to "http://localhost:11434"
        api_base_url (str): Base URL of the Meeting Transcriber API. Defaults to "http://localhost:8000"
        
    Returns:
        dict: Generated meeting notes with metadata including:
              - task_id: The transcription task ID
              - transcription_created_at: Timestamp of the transcription
              - notes_result: Contains the generated notes and metadata
        
    Raises:
        Exception: If note generation fails or times out (10 minutes)
    """
    params = {
        'template': template,
        'ollama_model': ollama_model,
        'ollama_base_url': ollama_base_url if ollama_base_url != "http://localhost:11434" else None
    }
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    
    # Make the API call - this will block until notes are generated
    response = requests.post(
        f"{api_base_url}/api/v1/generate-notes/{transcription_task_id}",
        params=params,
        timeout=300  # 5 minute timeout for note generation
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to generate notes: {response.status_code} - {response.text}")
    
    return response.json()

def main():
    """Command-line interface for the Meeting Transcriber helper functions."""
    import argparse
    import json
    import os
    
    parser = argparse.ArgumentParser(description='Meeting Transcriber CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Parser for transcribe_audio
    transcribe_parser = subparsers.add_parser('transcribe', help='Transcribe an audio file')
    transcribe_parser.add_argument('task_id', help='Processing task ID from upload_and_standardize_audio')
    transcribe_parser.add_argument('--hf-token', help='HuggingFace token for speaker diarization')
    transcribe_parser.add_argument('--whisper-model', help='Override default Whisper model')
    transcribe_parser.add_argument('--compute-type', help='Override compute type')
    transcribe_parser.add_argument('--api-base-url', default='http://localhost:8000',
                                 help='Base URL of the API (default: http://localhost:8000)')
    
    # Parser for generate_meeting_notes
    notes_parser = subparsers.add_parser('generate-notes', help='Generate meeting notes from transcription')
    notes_parser.add_argument('task_id', help='Transcription task ID')
    notes_parser.add_argument('--template', help='Custom template for note generation')
    notes_parser.add_argument('--ollama-model', help='Override default Ollama model')
    notes_parser.add_argument('--ollama-base-url', default='http://localhost:11434',
                          help='Ollama base URL (default: http://localhost:11434)')
    notes_parser.add_argument('--api-base-url', default='http://localhost:8000',
                            help='Base URL of the API (default: http://localhost:8000)')
    
    # Parser for upload_and_standardize_audio
    upload_parser = subparsers.add_parser('upload', help='Upload and standardize audio file')
    upload_parser.add_argument('file_path', help='Path to audio file')
    upload_parser.add_argument('--api-base-url', default='http://localhost:8000',
                             help='Base URL of the API (default: http://localhost:8000)')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'upload':
            task_id = upload_and_standardize_audio(args.file_path, args.api_base_url)
            print(json.dumps({"task_id": task_id, "status": "uploaded"}, indent=2))
            
        elif args.command == 'transcribe':
            result = transcribe_audio(
                processing_task_id=args.task_id,
                hf_token=args.hf_token or os.environ.get('HUGGINGFACE_TOKEN'),
                api_base_url=args.api_base_url,
                whisper_model=args.whisper_model,
                compute_type=args.compute_type
            )
            print(json.dumps(result, indent=2))
            
        elif args.command == 'generate-notes':
            result = generate_meeting_notes(
                transcription_task_id=args.task_id,
                template=args.template,
                ollama_model=args.ollama_model,
                ollama_base_url=args.ollama_base_url,
                api_base_url=args.api_base_url
            )
            print(json.dumps(result, indent=2))
            
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
