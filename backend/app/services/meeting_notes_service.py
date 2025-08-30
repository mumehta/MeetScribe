import os
import json
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from app.core.config import settings
from app.utils.timestamp_utils import generate_meeting_notes_filename, generate_human_readable_timestamp
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

class MeetingNotesService:
    def __init__(self):
        """Initialize the MeetingNotesService with Ollama model settings."""
        self.model_name = settings.OLLAMA_MODEL
        self.base_url = settings.OLLAMA_BASE_URL
        self.api_url = f"{self.base_url}/api/generate"
        
    async def generate_notes_from_transcript(self, transcript_segments: List[Dict], template: str = None, config_overrides: Dict[str, Any] = None, save_to_file: bool = False) -> Dict[str, Any]:
        """
        Generate meeting notes from transcript segments.
        
        Args:
            transcript_segments: List of transcript segments with speaker and text
            template: Optional template for the meeting notes format
            
        Returns:
            Dictionary containing generated meeting notes and metadata
        """
        config_overrides = config_overrides or {}
        
        # Use config overrides or defaults
        model_name = config_overrides.get('ollama_model', self.model_name)
        base_url = config_overrides.get('ollama_base_url', self.base_url)
        api_url = f"{base_url}/api/generate"
        
        # Convert segments to readable transcript
        transcript_text = self._format_transcript(transcript_segments)
        
        if template is None:
            template = self._get_default_template()
        
        prompt = template.format(transcript=transcript_text)
        
        try:
            logger.info(f"Generating meeting notes using Ollama model: {model_name}")
            response = requests.post(
                api_url,
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "max_tokens": 2000
                    }
                },
                timeout=120  # 2 minute timeout
            )
            response.raise_for_status()
            
            notes_content = response.json().get("response", "No response generated")
            
            # Save meeting notes to final output folder with timestamp if requested
            if save_to_file:
                timestamp = generate_human_readable_timestamp()
                filename = generate_meeting_notes_filename(timestamp)
                output_path = settings.final_output_folder_path / filename
                
                # Ensure final output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Format as markdown with metadata header
                markdown_content = f"# Meeting Notes\n\n**Generated:** {datetime.utcnow().isoformat()}\n**Model:** {model_name}\n**Transcript Length:** {len(transcript_segments)} segments\n\n---\n\n{notes_content}"
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                logger.info(f"Meeting notes saved to: {output_path}")
            
            return {
                "status": "completed",
                "notes": notes_content,
                "generated_at": datetime.utcnow().isoformat(),
                "model_used": model_name,
                "base_url_used": base_url,
                "transcript_length": len(transcript_segments)
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating notes: {str(e)}")
            return {
                "status": "error",
                "error": f"Error generating notes: {str(e)}",
                "generated_at": datetime.utcnow().isoformat()
            }
    
    def _format_transcript(self, segments: List[Dict]) -> str:
        """Format transcript segments into readable text."""
        formatted_lines = []
        
        for segment in segments:
            speaker = segment.get('speaker', 'UNKNOWN')
            text = segment.get('text', '').strip()
            start_time = segment.get('start', 0)
            
            # Format timestamp
            minutes = int(start_time // 60)
            seconds = int(start_time % 60)
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
            
            formatted_lines.append(f"{timestamp} {speaker}: {text}")
        
        return "\n".join(formatted_lines)
    
    def _get_default_template(self) -> str:
        """Get the default template for meeting notes generation."""
        return """Please analyze the following meeting transcript and generate comprehensive meeting notes. 
Include the following sections:
1. Meeting Summary (3-5 key points)
2. Key Discussion Points (bullet points)
3. Action Items (with assignees if mentioned)
4. Decisions Made
5. Next Steps/Follow-ups

Please format the output in clear markdown with proper headings and bullet points.

Transcript:
{transcript}"""
    
    async def check_ollama_availability(self, base_url: str = None) -> bool:
        """Check if Ollama service is available."""
        url = base_url or self.base_url
        try:
            response = requests.get(f"{url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

# Global service instance
meeting_notes_service = MeetingNotesService()
